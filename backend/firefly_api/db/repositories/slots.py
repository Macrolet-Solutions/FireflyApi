"""Repository for ``firefly_slots`` (§7.4).

Key business rules enforced here:

- ``slot_index`` is **server-assigned**, append-only per device. Clients must
  not send it (the schema does not include the field on Create/Update, so
  this is also blocked at the API edge).
- ``segment_id`` and ``segment_position`` are immutable on PUT.
- Mutable PUT fields are ``external_slot_id``, ``label``, ``num_leds``. A
  ``num_leds`` change re-checks the in-segment overlap rule.
- The slot's LED range ``[segment_position, segment_position + num_leds - 1]``
  must fit inside the segment, and must not overlap any sibling slot in the
  same segment.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from firefly_api.core.errors import ConflictError, NotFoundError, ValidationFailedError
from firefly_api.db.models import FireflySegment, FireflySlot
from firefly_api.db.repositories import devices as devices_repo
from firefly_api.schemas.slots import FireflySlotCreate, FireflySlotUpdate


def list_for_device(db: Session, device_id: int) -> list[FireflySlot]:
    devices_repo.get_by_id(db, device_id)
    return list(
        db.scalars(
            select(FireflySlot)
            .where(FireflySlot.device_id == device_id)
            .order_by(FireflySlot.slot_index)
        )
    )


def get_by_id(db: Session, device_id: int, slot_id: int) -> FireflySlot:
    slot = db.get(FireflySlot, slot_id)
    if slot is None or slot.device_id != device_id:
        raise NotFoundError(
            f"Slot {slot_id} not found for device {device_id}.",
            error_code="slot_not_found",
        )
    return slot


def _next_slot_index(db: Session, device_id: int) -> int:
    """Return the next free 1-based ``slot_index`` for the device (append-only)."""
    current_max = db.scalar(
        select(FireflySlot.slot_index)
        .where(FireflySlot.device_id == device_id)
        .order_by(FireflySlot.slot_index.desc())
        .limit(1)
    )
    return (current_max or 0) + 1


def _segment_for_device(db: Session, device_id: int, segment_id: int) -> FireflySegment:
    segment = db.get(FireflySegment, segment_id)
    if segment is None or segment.device_id != device_id:
        raise ValidationFailedError(
            f"Segment {segment_id} does not belong to device {device_id}.",
            error_code="invalid_segment_id",
        )
    return segment


def _check_fits_and_no_overlap(
    *,
    segment: FireflySegment,
    segment_position: int,
    num_leds: int,
    siblings: list[FireflySlot],
    exclude_slot_id: int | None = None,
) -> None:
    last = segment_position + num_leds - 1
    if last > segment.led_count:
        raise ValidationFailedError(
            (
                f"Slot range [{segment_position}, {last}] exceeds segment "
                f"capacity of {segment.led_count} LEDs."
            ),
            error_code="slot_out_of_segment",
        )
    for sibling in siblings:
        if exclude_slot_id is not None and sibling.id == exclude_slot_id:
            continue
        s_first = sibling.segment_position
        s_last = sibling.segment_position + sibling.num_leds - 1
        if s_first <= last and segment_position <= s_last:
            raise ValidationFailedError(
                (
                    f"Slot range [{segment_position}, {last}] overlaps "
                    f"slot {sibling.id} [{s_first}, {s_last}]."
                ),
                error_code="slot_overlap",
                details={"conflicting_slot_id": sibling.id},
            )


def create(db: Session, device_id: int, data: FireflySlotCreate) -> FireflySlot:
    devices_repo.get_by_id(db, device_id)
    segment = _segment_for_device(db, device_id, data.segment_id)
    _check_fits_and_no_overlap(
        segment=segment,
        segment_position=data.segment_position,
        num_leds=data.num_leds,
        siblings=list(segment.slots),
    )
    slot = FireflySlot(
        device_id=device_id,
        segment_id=data.segment_id,
        slot_index=_next_slot_index(db, device_id),
        external_slot_id=data.external_slot_id,
        label=data.label,
        segment_position=data.segment_position,
        num_leds=data.num_leds,
    )
    db.add(slot)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError(
            f"external_slot_id '{data.external_slot_id}' already in use on device "
            f"{device_id}.",
            error_code="external_slot_id_conflict",
        ) from exc
    db.refresh(slot)
    return slot


def update(
    db: Session,
    device_id: int,
    slot_id: int,
    data: FireflySlotUpdate,
) -> FireflySlot:
    slot = get_by_id(db, device_id, slot_id)
    segment = slot.segment  # immutable on PUT, so reuse
    if data.num_leds != slot.num_leds:
        _check_fits_and_no_overlap(
            segment=segment,
            segment_position=slot.segment_position,
            num_leds=data.num_leds,
            siblings=list(segment.slots),
            exclude_slot_id=slot.id,
        )
    slot.external_slot_id = data.external_slot_id
    slot.label = data.label
    slot.num_leds = data.num_leds
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError(
            f"external_slot_id '{data.external_slot_id}' already in use on device "
            f"{device_id}.",
            error_code="external_slot_id_conflict",
        ) from exc
    db.refresh(slot)
    return slot


def delete(db: Session, device_id: int, slot_id: int) -> None:
    slot = get_by_id(db, device_id, slot_id)
    db.delete(slot)
    db.commit()
