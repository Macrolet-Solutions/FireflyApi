"""Repository for ``firefly_slots`` (§7.4).

Key business rules enforced here:

- ``slot_index`` is **server-assigned** per device. Clients must not send it
    (the schema does not include the field on Create/Update, so this is also
    blocked at the API edge). It is compacted after deletes so firmware always
    receives a gap-free 1-based sequence across the whole controller/device.
- ``segment_id`` and ``segment_position`` are immutable on PUT.
- Mutable PUT fields are ``external_slot_id``, ``label``, ``num_leds``. A
    ``num_leds`` change re-checks the segment capacity rule.
- ``segment_position`` is the slot's relative position within the segment, not
    a starting LED index. Slots in a segment are physically adjacent, so the total
    configured slot LED count must fit inside the segment and positions must be
    unique within the segment.
"""

from __future__ import annotations

from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from firefly_api.core.errors import ConflictError, NotFoundError, ValidationFailedError
from firefly_api.db.models import (
    SEGMENT_MODE_DYNAMIC,
    FireflySegment,
    FireflySlot,
)
from firefly_api.db.repositories import devices as devices_repo
from firefly_api.schemas.slots import (
    FireflySlotCreate,
    FireflySlotImportRow,
    FireflySlotUpdate,
)


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
    """Return the next 1-based ``slot_index`` for the device."""
    current_max = db.scalar(
        select(FireflySlot.slot_index)
        .where(FireflySlot.device_id == device_id)
        .order_by(FireflySlot.slot_index.desc())
        .limit(1)
    )
    return (current_max or 0) + 1


def _compact_slot_indexes(db: Session, device_id: int) -> None:
    slots = list(
        db.scalars(
            select(FireflySlot)
            .where(FireflySlot.device_id == device_id)
            .order_by(FireflySlot.slot_index, FireflySlot.id)
        )
    )
    if not slots:
        return

    temp_index = max(slot.slot_index for slot in slots) + len(slots) + 1
    for offset, slot in enumerate(slots):
        slot.slot_index = temp_index + offset
    db.flush()

    for index, slot in enumerate(slots, start=1):
        slot.slot_index = index


def _segment_for_device(db: Session, device_id: int, segment_id: int) -> FireflySegment:
    segment = db.get(FireflySegment, segment_id)
    if segment is None or segment.device_id != device_id:
        raise ValidationFailedError(
            f"Segment {segment_id} does not belong to device {device_id}.",
            error_code="invalid_segment_id",
        )
    return segment


def _ensure_static_segment(segment: FireflySegment) -> None:
    if segment.mode == SEGMENT_MODE_DYNAMIC:
        raise ValidationFailedError(
            (
                f"Segment {segment.id} is dynamic. Load its slots through the "
                "public load-slots endpoint."
            ),
            error_code="dynamic_segment_slots_not_allowed",
        )


def _check_position_and_capacity(
    *,
    segment: FireflySegment,
    segment_position: int,
    num_leds: int,
    siblings: list[FireflySlot],
    exclude_slot_id: int | None = None,
) -> None:
    total_leds = num_leds
    for sibling in siblings:
        if exclude_slot_id is not None and sibling.id == exclude_slot_id:
            continue
        if sibling.segment_position == segment_position:
            raise ValidationFailedError(
                (
                    f"Slot position {segment_position} is already used by "
                    f"slot {sibling.id}."
                ),
                error_code="slot_position_conflict",
                details={"conflicting_slot_id": sibling.id},
            )
        total_leds += sibling.num_leds

    if total_leds > segment.led_count:
        raise ValidationFailedError(
            (
                f"Total slot LEDs ({total_leds}) exceeds segment capacity "
                f"of {segment.led_count} LEDs."
            ),
            error_code="slot_out_of_segment",
        )


def create(db: Session, device_id: int, data: FireflySlotCreate) -> FireflySlot:
    devices_repo.get_by_id(db, device_id)
    segment = _segment_for_device(db, device_id, data.segment_id)
    _ensure_static_segment(segment)
    _check_position_and_capacity(
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


def replace_for_device(
    db: Session,
    device_id: int,
    rows: list[FireflySlotImportRow],
) -> list[FireflySlot]:
    devices_repo.get_by_id(db, device_id)
    segments = list(
        db.scalars(
            select(FireflySegment).where(FireflySegment.device_id == device_id)
        )
    )
    segment_by_key = {
        (segment.channel_num, segment.segment_num_in_channel): segment
        for segment in segments
    }
    import_errors: list[dict[str, object]] = []
    external_slot_rows: dict[str, int] = {}
    segment_position_rows: dict[tuple[int, int], int] = {}
    led_totals: defaultdict[int, int] = defaultdict(int)
    segment_by_row: list[FireflySegment | None] = []

    for index, row in enumerate(rows, start=1):
        external_seen_at = external_slot_rows.get(row.external_slot_id)
        if external_seen_at is not None:
            import_errors.append(
                {
                    "row": index,
                    "field": "external_slot_id",
                    "message": (
                        f"Duplicate external_slot_id also used on row "
                        f"{external_seen_at}."
                    ),
                }
            )
        else:
            external_slot_rows[row.external_slot_id] = index

        segment = segment_by_key.get((row.channel_num, row.segment_num_in_channel))
        segment_by_row.append(segment)
        if segment is None:
            import_errors.append(
                {
                    "row": index,
                    "field": "channel_num,segment_num_in_channel",
                    "message": (
                        f"Segment ch {row.channel_num} / seg "
                        f"{row.segment_num_in_channel} does not exist."
                    ),
                }
            )
            continue
        if segment.mode == SEGMENT_MODE_DYNAMIC:
            import_errors.append(
                {
                    "row": index,
                    "field": "channel_num,segment_num_in_channel",
                    "message": (
                        f"Segment ch {row.channel_num} / seg "
                        f"{row.segment_num_in_channel} is dynamic."
                    ),
                }
            )
            continue

        position_key = (segment.id, row.segment_position)
        position_seen_at = segment_position_rows.get(position_key)
        if position_seen_at is not None:
            import_errors.append(
                {
                    "row": index,
                    "field": "segment_position",
                    "message": (
                        f"Duplicate position for this segment also used on row "
                        f"{position_seen_at}."
                    ),
                }
            )
        else:
            segment_position_rows[position_key] = index
        led_totals[segment.id] += row.num_leds

    segment_by_id = {segment.id: segment for segment in segments}
    for segment_id, total_leds in led_totals.items():
        segment = segment_by_id[segment_id]
        if total_leds > segment.led_count:
            import_errors.append(
                {
                    "field": "num_leds",
                    "message": (
                        f"Total slot LEDs ({total_leds}) for ch "
                        f"{segment.channel_num} / seg "
                        f"{segment.segment_num_in_channel} exceeds segment "
                        f"capacity of {segment.led_count} LEDs."
                    ),
                }
            )

    if import_errors:
        raise ValidationFailedError(
            "Slot CSV import failed validation.",
            error_code="slot_import_invalid",
            details={"errors": import_errors},
        )

    existing_slots = list(
        db.scalars(select(FireflySlot).where(FireflySlot.device_id == device_id))
    )
    for slot in existing_slots:
        db.delete(slot)
    db.flush()

    new_slots = [
        FireflySlot(
            device_id=device_id,
            segment_id=segment_by_row[index].id,
            slot_index=index + 1,
            external_slot_id=row.external_slot_id,
            label=row.label,
            segment_position=row.segment_position,
            num_leds=row.num_leds,
        )
        for index, row in enumerate(rows)
        if segment_by_row[index] is not None
    ]
    db.add_all(new_slots)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError(
            "Imported slot configuration violates a database constraint.",
            error_code="slot_import_conflict",
        ) from exc
    return list_for_device(db, device_id)


def replace_dynamic_segments(
    db: Session,
    device_id: int,
    segments_in: list[dict],
) -> list[FireflySlot]:
    devices_repo.get_by_id(db, device_id)
    segments = list(
        db.scalars(
            select(FireflySegment).where(FireflySegment.device_id == device_id)
        )
    )
    segment_by_key = {
        (segment.channel_num, segment.segment_num_in_channel): segment
        for segment in segments
    }

    errors: list[dict[str, object]] = []
    seen_segments: dict[tuple[int, int], int] = {}
    target_segments: list[FireflySegment] = []
    led_totals: defaultdict[int, int] = defaultdict(int)
    new_external_ids: dict[str, tuple[int, int]] = {}

    for segment_index, segment_in in enumerate(segments_in, start=1):
        key = (segment_in["channel_num"], segment_in["segment_num_in_channel"])
        seen_at = seen_segments.get(key)
        if seen_at is not None:
            errors.append(
                {
                    "segment": segment_index,
                    "field": "channelNum,segmentNumInChannel",
                    "message": f"Duplicate segment also used at index {seen_at}.",
                }
            )
            continue
        seen_segments[key] = segment_index

        segment = segment_by_key.get(key)
        if segment is None:
            errors.append(
                {
                    "segment": segment_index,
                    "field": "channelNum,segmentNumInChannel",
                    "message": (
                        f"Segment ch {key[0]} / seg {key[1]} does not exist."
                    ),
                }
            )
            continue
        if segment.mode != SEGMENT_MODE_DYNAMIC:
            errors.append(
                {
                    "segment": segment_index,
                    "field": "channelNum,segmentNumInChannel",
                    "message": f"Segment ch {key[0]} / seg {key[1]} is not dynamic.",
                }
            )
            continue

        target_segments.append(segment)
        for slot_index, slot_in in enumerate(segment_in["slots"], start=1):
            external_slot_id = slot_in["external_slot_id"]
            duplicate = new_external_ids.get(external_slot_id)
            if duplicate is not None:
                errors.append(
                    {
                        "segment": segment_index,
                        "slot": slot_index,
                        "field": "externalSlotId",
                        "message": (
                            "Duplicate externalSlotId also used at segment "
                            f"{duplicate[0]}, slot {duplicate[1]}."
                        ),
                    }
                )
            else:
                new_external_ids[external_slot_id] = (segment_index, slot_index)
            led_totals[segment.id] += slot_in["num_leds"]

    target_segment_ids = {segment.id for segment in target_segments}
    for segment in target_segments:
        total_leds = led_totals[segment.id]
        if total_leds > segment.led_count:
            errors.append(
                {
                    "field": "numLeds",
                    "message": (
                        f"Total slot LEDs ({total_leds}) for ch "
                        f"{segment.channel_num} / seg "
                        f"{segment.segment_num_in_channel} exceeds segment "
                        f"capacity of {segment.led_count} LEDs."
                    ),
                }
            )

    unaffected_slots = list(
        db.scalars(
            select(FireflySlot).where(
                FireflySlot.device_id == device_id,
                FireflySlot.segment_id.not_in(target_segment_ids),
            )
        )
    )
    unaffected_external_ids = {slot.external_slot_id for slot in unaffected_slots}
    for external_slot_id, (segment_index, slot_index) in new_external_ids.items():
        if external_slot_id in unaffected_external_ids:
            errors.append(
                {
                    "segment": segment_index,
                    "slot": slot_index,
                    "field": "externalSlotId",
                    "message": (
                        f"externalSlotId '{external_slot_id}' is already used "
                        "outside the loaded dynamic segments."
                    ),
                }
            )

    if errors:
        raise ValidationFailedError(
            "Dynamic slot layout failed validation.",
            error_code="dynamic_slot_layout_invalid",
            details={"errors": errors},
        )

    existing_slots = list(
        db.scalars(select(FireflySlot).where(FireflySlot.device_id == device_id))
    )
    for slot in existing_slots:
        if slot.segment_id in target_segment_ids:
            db.delete(slot)
    db.flush()

    target_segment_by_key = {
        (segment.channel_num, segment.segment_num_in_channel): segment
        for segment in target_segments
    }
    temp_slot_index = max((slot.slot_index for slot in existing_slots), default=0) + 1
    new_slots: list[FireflySlot] = []
    for segment_in in segments_in:
        segment = target_segment_by_key.get(
            (segment_in["channel_num"], segment_in["segment_num_in_channel"])
        )
        if segment is None:
            continue
        for position, slot_in in enumerate(segment_in["slots"], start=1):
            new_slots.append(
                FireflySlot(
                    device_id=device_id,
                    segment_id=segment.id,
                    slot_index=temp_slot_index,
                    external_slot_id=slot_in["external_slot_id"],
                    label=slot_in["external_slot_id"],
                    segment_position=position,
                    num_leds=slot_in["num_leds"],
                )
            )
            temp_slot_index += 1
    db.add_all(new_slots)
    try:
        db.flush()
        _compact_slot_indexes(db, device_id)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError(
            "Dynamic slot layout violates a database constraint.",
            error_code="dynamic_slot_layout_conflict",
        ) from exc
    return list_for_device(db, device_id)


def update(
    db: Session,
    device_id: int,
    slot_id: int,
    data: FireflySlotUpdate,
) -> FireflySlot:
    slot = get_by_id(db, device_id, slot_id)
    segment = slot.segment  # immutable on PUT, so reuse
    _ensure_static_segment(segment)
    if data.num_leds != slot.num_leds:
        _check_position_and_capacity(
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
    _ensure_static_segment(slot.segment)
    db.delete(slot)
    db.flush()
    _compact_slot_indexes(db, device_id)
    db.commit()
