"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-05-11

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "mqtt_brokers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("host", sa.String(length=255), nullable=False),
        sa.Column("port", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(length=255), nullable=True),
        sa.Column("password", sa.String(length=255), nullable=True),
        sa.Column("use_tls", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("client_id", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("name", name="uq_mqtt_brokers_name"),
    )

    op.create_table(
        "firefly_devices",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("mqtt_broker_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["mqtt_broker_id"],
            ["mqtt_brokers.id"],
            name="fk_firefly_devices_mqtt_broker_id",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("name", name="uq_firefly_devices_name"),
    )

    op.create_table(
        "firefly_segments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("device_id", sa.Integer(), nullable=False),
        sa.Column("channel_num", sa.Integer(), nullable=False),
        sa.Column("segment_num_in_channel", sa.Integer(), nullable=False),
        sa.Column("first_led_index", sa.Integer(), nullable=False),
        sa.Column("last_led_index", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["device_id"],
            ["firefly_devices.id"],
            name="fk_firefly_segments_device_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "device_id",
            "channel_num",
            "segment_num_in_channel",
            name="uq_firefly_segments_device_channel_segment",
        ),
        sa.CheckConstraint("first_led_index >= 1", name="ck_firefly_segments_first_led_ge_1"),
        sa.CheckConstraint("last_led_index >= 1", name="ck_firefly_segments_last_led_ge_1"),
    )

    op.create_table(
        "firefly_slots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("device_id", sa.Integer(), nullable=False),
        sa.Column("segment_id", sa.Integer(), nullable=False),
        sa.Column("slot_index", sa.Integer(), nullable=False),
        sa.Column("external_slot_id", sa.String(length=64), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=True),
        sa.Column("segment_position", sa.Integer(), nullable=False),
        sa.Column("num_leds", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["device_id"],
            ["firefly_devices.id"],
            name="fk_firefly_slots_device_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["segment_id"],
            ["firefly_segments.id"],
            name="fk_firefly_slots_segment_id",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "device_id", "slot_index", name="uq_firefly_slots_device_slot_index"
        ),
        sa.UniqueConstraint(
            "device_id",
            "external_slot_id",
            name="uq_firefly_slots_device_external_slot_id",
        ),
        sa.CheckConstraint("slot_index >= 1", name="ck_firefly_slots_slot_index_ge_1"),
        sa.CheckConstraint(
            "segment_position >= 1", name="ck_firefly_slots_segment_position_ge_1"
        ),
        sa.CheckConstraint("num_leds >= 1", name="ck_firefly_slots_num_leds_ge_1"),
    )

    op.create_table(
        "firefly_led_states",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("rgb", sa.String(length=8), nullable=False),
        sa.Column("color1_on_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("color1_fade_up_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("color1_fade_down_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("repeat_after_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("num_repetitions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("name", name="uq_firefly_led_states_name"),
    )

    op.create_table(
        "firefly_command_presets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("led_state_id", sa.Integer(), nullable=False),
        sa.Column("pattern", sa.Integer(), nullable=False),
        sa.Column("pattern_value", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["led_state_id"],
            ["firefly_led_states.id"],
            name="fk_firefly_command_presets_led_state_id",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("name", name="uq_firefly_command_presets_name"),
        sa.CheckConstraint(
            "pattern BETWEEN 0 AND 4",
            name="ck_firefly_command_presets_pattern_range",
        ),
        sa.CheckConstraint(
            "pattern_value >= 0",
            name="ck_firefly_command_presets_pattern_value_ge_0",
        ),
    )

    op.create_table(
        "firefly_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("device_id", sa.Integer(), nullable=False),
        sa.Column("event_id", sa.String(length=36), nullable=False),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=True),
        sa.Column("payload_json", sa.JSON(), nullable=True),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("error_description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["device_id"],
            ["firefly_devices.id"],
            name="fk_firefly_events_device_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_firefly_events_device_created",
        "firefly_events",
        ["device_id", "created_at"],
    )
    op.create_index("ix_firefly_events_event_id", "firefly_events", ["event_id"])


def downgrade() -> None:
    op.drop_index("ix_firefly_events_event_id", table_name="firefly_events")
    op.drop_index("ix_firefly_events_device_created", table_name="firefly_events")
    op.drop_table("firefly_events")
    op.drop_table("firefly_command_presets")
    op.drop_table("firefly_led_states")
    op.drop_table("firefly_slots")
    op.drop_table("firefly_segments")
    op.drop_table("firefly_devices")
    op.drop_table("mqtt_brokers")
