"""Repository for ``firefly_segments`` (§7.3).

Validation rules enforced here:

- Within a device, ``(channel_num, segment_num_in_channel)`` must be unique
  (enforced at the DB layer).
- ``first_led_index`` and ``last_led_index`` must be ``>= 1`` (DB check).
- Segments on the same ``channel_num`` of the same device must not overlap in
  their LED range, regardless of direction (enforced here in Python so we can
  emit a descriptive 422).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from firefly_api.core.errors import ConflictError, NotFoundError, ValidationFailedError
from firefly_api.db.models import FireflySegment, FireflySlot
from firefly_api.db.repositories import devices as devices_repo
from firefly_api.schemas.segments import FireflySegmentCreate, FireflySegmentUpdate


def _bounds(first: int, last: int) -> tuple[int, int]:
    return (min(first, last), max(first, last))


def _ranges_overlap(a_first: int, a_last: int, b_first: int, b_last: int) -> bool:
    a_lo, a_hi = _bounds(a_first, a_last)
    b_lo, b_hi = _bounds(b_first, b_last)
    return a_lo <= b_hi and b_lo <= a_hi


def list_for_device(db: Session, device_id: int) -> list[FireflySegment]:
    devices_repo.get_by_id(db, device_id)
    return list(
        db.scalars(
            select(FireflySegment)
            .where(FireflySegment.device_id == device_id)
            .order_by(FireflySegment.id)
        )
    )


def get_by_id(db: Session, device_id: int, segment_id: int) -> FireflySegment:
    segment = db.get(FireflySegment, segment_id)
    if segment is None or segment.device_id != device_id:
        raise NotFoundError(
            f"Segment {segment_id} not found for device {device_id}.",
            error_code="segment_not_found",
        )
    return segment


def _check_no_channel_overlap(
    db: Session,
    *,
    device_id: int,
    channel_num: int,
    first_led_index: int,
    last_led_index: int,
    exclude_segment_id: int | None = None,
) -> None:
    siblings = db.scalars(
        select(FireflySegment).where(
            FireflySegment.device_id == device_id,
            FireflySegment.channel_num == channel_num,
        )
    )
    for sibling in siblings:
        if exclude_segment_id is not None and sibling.id == exclude_segment_id:
            continue
        if _ranges_overlap(
            first_led_index,
            last_led_index,
            sibling.first_led_index,
            sibling.last_led_index,
        ):
            raise ValidationFailedError(
                (
                    f"Segment LED range [{first_led_index}, {last_led_index}] "
                    f"overlaps existing segment {sibling.id} "
                    f"[{sibling.first_led_index}, {sibling.last_led_index}] "
                    f"on channel {channel_num}."
                ),
                error_code="segment_overlap",
                details={"conflicting_segment_id": sibling.id},
            )


def create(db: Session, device_id: int, data: FireflySegmentCreate) -> FireflySegment:
    devices_repo.get_by_id(db, device_id)
    _check_no_channel_overlap(
        db,
        device_id=device_id,
        channel_num=data.channel_num,
        first_led_index=data.first_led_index,
        last_led_index=data.last_led_index,
    )
    segment = FireflySegment(device_id=device_id, **data.model_dump())
    db.add(segment)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError(
            (
                f"Segment (channel {data.channel_num}, "
                f"segment_num_in_channel {data.segment_num_in_channel}) "
                f"already exists for device {device_id}."
            ),
            error_code="segment_conflict",
        ) from exc
    db.refresh(segment)
    return segment


def update(
    db: Session,
    device_id: int,
    segment_id: int,
    data: FireflySegmentUpdate,
) -> FireflySegment:
    segment = get_by_id(db, device_id, segment_id)
    _check_no_channel_overlap(
        db,
        device_id=device_id,
        channel_num=data.channel_num,
        first_led_index=data.first_led_index,
        last_led_index=data.last_led_index,
        exclude_segment_id=segment_id,
    )
    # If the segment's LED range or channel changes, the adjacent slot layout
    # within it must still fit. We enforce this explicitly.
    new_count = abs(data.last_led_index - data.first_led_index) + 1
    total_slot_leds = sum(slot.num_leds for slot in segment.slots)
    if total_slot_leds > new_count:
        raise ValidationFailedError(
            (
                f"Configured slot LEDs ({total_slot_leds}) would no longer fit "
                f"in the resized segment ({new_count} LEDs)."
            ),
            error_code="slot_overflow_after_segment_resize",
        )
    for field, value in data.model_dump().items():
        setattr(segment, field, value)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError(
            (
                f"Segment (channel {data.channel_num}, "
                f"segment_num_in_channel {data.segment_num_in_channel}) "
                f"already exists for device {device_id}."
            ),
            error_code="segment_conflict",
        ) from exc
    db.refresh(segment)
    return segment


def delete(db: Session, device_id: int, segment_id: int) -> None:
    segment = get_by_id(db, device_id, segment_id)
    slot_count = db.scalar(
        select(FireflySlot.id).where(FireflySlot.segment_id == segment_id).limit(1)
    )
    if slot_count is not None:
        raise ConflictError(
            f"Segment {segment_id} is referenced by one or more slots.",
            error_code="segment_in_use",
        )
    db.delete(segment)
    db.commit()
