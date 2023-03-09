#!/usr/bin/env python3
from __future__ import annotations

from abc import ABC, abstractmethod
import argparse
from collections.abc import Collection, Generator, Iterable, Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass
import datetime as dt
from enum import Enum
from itertools import cycle
import json
from os.path import basename
from pathlib import Path
import re
from shutil import get_terminal_size
import sqlite3
import sys
from typing import Any, TypeVar, cast

from ordered_set import OrderedSet
from termcolor import colored, cprint


DEF_DATABASE = "~/homeassistant/production/config/home-assistant_v2.db"
CORE_EVENTS = [
    "homeassistant_start",
    "homeassistant_started",
    "homeassistant_stop",
    "core_config_updated",
]
REGEX_PREFIX = "%"

COL1_HEADER = "entity_id / event_type"
TS_HEADER = "last_updated / time_fired"
TS_WIDTH = 26
STATE_HEADER = "state"
ATTRS_HEADER = "attributes"
COL_SEP = " | "
HDR_SEP = "-|-"
MISSING = "¿¿¿"
COLORS_STOP = ("white", "on_red")
COLORS_HA_EVENT = ("black", "on_cyan")
COLORS_USER_EVENT = ("black", "on_yellow")
COLOR_BANNER = "light_green"
COLORS_STATES = [
    "light_magenta",
    "light_blue",
    "light_green",
    "light_cyan",
    "light_red",
    "light_yellow",
    "magenta",
    "green",
    "cyan",
    "red",
    "yellow",
]
COLORS_TS = ["light_grey", "white"]

Items = Mapping[str, Any]


def print_msg(
    text: str,
    color: str | None = None,
    on_color: str | None = None,
    attrs: Iterable[str] | None = None,
    prefix: str | None = "error",
    usage: bool = True,
    **kwargs: Any,
) -> None:
    """Print error message to stderr."""
    if usage:
        print_usage(file=sys.stderr)
    if prefix is None:
        prefix = ""
    else:
        prefix = f" {prefix}:"
    cprint(
        f"{basename(sys.argv[0])}:{prefix} {text}",
        color=color,
        on_color=on_color,
        attrs=attrs,
        **kwargs,
        file=sys.stderr,
    )


def find_stop(stops: int) -> dt.datetime | None:
    """Find time HA stopped # of times ago."""
    result = con.execute(
        "SELECT time_fired_ts FROM events"
        " WHERE event_type = 'homeassistant_stop'"
        " ORDER BY time_fired_ts DESC LIMIT ?",
        (stops,),
    ).fetchall()
    if len(result) != stops:
        return None
    return dt.datetime.fromtimestamp(result[-1][0])


def get_oldest(column: str, table: str) -> dt.datetime:
    """Get oldest value from table column."""
    return dt.datetime.fromtimestamp(
        con.execute(
            "SELECT {column} FROM {table} ORDER BY {column} LIMIT 1".format(
                column=column,
                table=table,
            )
        ).fetchone()[0]
    )


def get_schema_version() -> int:
    """Get schema version."""
    return int(
        con.execute(
            "SELECT schema_version FROM schema_changes"
            " ORDER BY schema_version DESC LIMIT 1"
        ).fetchone()[0]
    )


def get_unique(column: str, table: str) -> list[str]:
    """Get all unique values from table column."""
    try:
        return list(
            zip(*con.execute(f"SELECT DISTINCT {column} FROM {table}").fetchall())
        )[0]
    except IndexError:
        return set()


def where(
    keys: Sequence[str],
    start: dt.datetime | None = None,
    end: dt.datetime | None = None,
) -> str:
    """Create WHERE clause."""
    exprs: list[str] = []
    if len(keys) == 1:
        exprs.append(f"key = '{keys[0]}'")
    elif len(keys) > 1:
        exprs.append(f"key IN {repr(tuple(keys))}")
    if start is not None:
        exprs.append(f"ts >= {start.timestamp()}")
    if end is not None:
        exprs.append(f"ts < {end.timestamp()}")
    return f"WHERE {' AND '.join(exprs)}" if exprs else ""


def find_oldest() -> dt.datetime:
    """Find oldest event or state update."""

    oldest_state_update = get_oldest("last_updated_ts", "states")
    oldest_event = get_oldest("time_fired_ts", "events")
    return min(oldest_state_update, oldest_event)


def today_at(time: dt.time = dt.time()) -> dt.datetime:
    """Return datetime for today at specified time or midnight this morning."""
    return dt.datetime.combine(dt.datetime.now().date(), time)


class NameValueExprError(Exception):
    """Name/value expression error."""


class NameValueOp(Enum):
    """Name/value operator."""

    ALL_EQ = "=="
    ANY_EQ = "="


class NameValueExpr:
    """Name/value expression."""

    _name: re.Pattern | str
    _op: NameValueOp | None = None
    _value: re.Pattern | str | float | None = None

    def __init__(
        self,
        nv_expr_str: str,
        name_regex_ok: bool = True,
        filter_ok: bool = True,
    ) -> None:
        """Initialize."""
        if not name_regex_ok and nv_expr_str.startswith(REGEX_PREFIX):
            raise NameValueExprError("name may not be a regex")

        def convert(
            s_or_r: str, extended_ok: bool = True
        ) -> re.Pattern[str] | str | float:
            """Convert to appropriate type."""
            if s_or_r.startswith(REGEX_PREFIX):
                regex = s_or_r[1:]
                try:
                    return re.compile(regex)
                except re.error as exc:
                    raise NameValueExprError(
                        f"invalid regex: {regex!r}: {exc}"
                    ) from exc
            if extended_ok:
                with suppress(TypeError, ValueError):
                    return float(s_or_r)
            return s_or_r

        self._name = nv_expr_str
        for nv_op in NameValueOp:
            with suppress(ValueError):
                self._name, self._value = nv_expr_str.split(nv_op.value)
                self._op = nv_op
                self._value = convert(self._value)
                break
        if not filter_ok and self._op is not None:
            raise NameValueExprError("filter not allowed")
        self._name = cast(re.Pattern | str, convert(self._name, extended_ok=False))

    def __repr__(self) -> str:
        """Return representation string."""
        return (
            f"{self.__class__.__name__}"
            f"(name={self._name!r}, op={self._op}, value={self._value!r})"
        )

    @property
    def name_is_regex(self) -> bool:
        """Return if name is a regex."""
        return isinstance(self._name, re.Pattern)

    @property
    def name(self) -> re.Pattern | str:
        """Return name."""
        return self._name

    def name_matches(self, name: str) -> bool:
        """Return if name matches name expression."""
        if isinstance(self._name, re.Pattern):
            return bool(self._name.fullmatch(name))
        return self._name == name

    def matching_names(self, all_names: Iterable[str]) -> OrderedSet[str]:
        """Return names that match name expression."""
        if not self.name_is_regex:
            return OrderedSet([self._name])
        return OrderedSet(filter(self.name_matches, all_names))

    def item_matches(self, name: str, value: Any) -> bool:
        """Return if name & value match expressions."""
        return self.name_matches(name) and self._value_matches(value)

    def filter_items(self, items: Items) -> tuple[bool, Items]:
        """
        Return items that match name expression,
        and of those, if values match value expression, if any.
        """
        if not self.name_is_regex:
            value = items.get(self._name, MISSING)
            return self._value_matches(value), {self._name: value}

        name_matching_items = cast(
            Items, dict(filter(self._item_name_matches, items.items()))
        )
        if self._op is None:
            return True, name_matching_items

        assert self._op in [NameValueOp.ALL_EQ, NameValueOp.ANY_EQ]
        n_value_matches = sum(
            map(self._item_value_matches, name_matching_items.items())
        )
        match self._op:
            case op if "ANY" in op.name:
                matches = n_value_matches >= 1
            case op if "ALL" in op.name:
                matches = n_value_matches == len(name_matching_items)
        return matches, name_matching_items

    def _value_matches(self, value: Any) -> bool:
        """Return if value matches value expression."""
        if self._op is None:
            return True
        assert self._op in [NameValueOp.ALL_EQ, NameValueOp.ANY_EQ]
        assert self._value is not None
        if isinstance(self._value, re.Pattern):
            return bool(self._value.fullmatch(str(value)))
        if isinstance(self._value, float):
            with suppress(TypeError, ValueError):
                return self._value == float(value)
        return str(self._value) == str(value)

    def _item_name_matches(self, item_tuple: tuple[str, Any]) -> bool:
        """Return if name part of item tuple matches name expression."""
        return self.name_matches(item_tuple[0])

    def _item_value_matches(self, item_tuple: tuple[str, Any]) -> bool:
        """Return if value part of item tuple matches name expression."""
        return self._value_matches(item_tuple[1])


class NameValueExprs(list[NameValueExpr]):
    """Multiple name/value expressions."""

    def __init__(
        self, nv_expr_strs: Collection[str] | None = None, name_regex_ok: bool = True
    ) -> None:
        nv_exprs = [
            NameValueExpr(nv_expr_str, name_regex_ok)
            for nv_expr_str in nv_expr_strs or []
        ]
        super().__init__(nv_exprs)

    @property
    def all_str_names(self) -> OrderedSet[str]:
        """Return all non-regex names."""
        return OrderedSet(
            map(
                lambda nv_expr: nv_expr.name,
                filter(lambda nv_expr: not nv_expr.name_is_regex, self),
            )
        )

    def matching_names(self, all_names: Iterable[str]) -> OrderedSet[str]:
        """Return names that match any name expression."""
        sets = [nv_expr.matching_names(all_names) for nv_expr in self]
        if not sets:
            return OrderedSet()
        return OrderedSet.union(*sets)

    def filter_items(self, items: Items) -> tuple[bool, Items]:
        """Return filter results of all all expressions."""
        all_match = True
        all_name_matching_items: Items = {}
        for nv_expr in self:
            matches, name_matching_items = nv_expr.filter_items(items)
            all_match &= matches
            all_name_matching_items.update(name_matching_items)
        return all_match, all_name_matching_items


TRow = TypeVar("TRow", bound="Row")


class Row(ABC):
    """Timestamped ID, items & optional value."""

    @abstractmethod
    def __init__(
        self, ts: dt.datetime, id: str, items: Items, value: str | None = None
    ) -> None:
        """Initialize."""
        self.ts = ts
        self.id = id
        self.items = items
        self.value = value

    @classmethod
    def from_db_values(
        cls: type[TRow], ts: float, id: str, items: str, value: str | None = None
    ) -> TRow:
        """Create object from raw database values."""
        args = (dt.datetime.fromtimestamp(ts), id, cast(Items, json.loads(items)))
        if value is None:
            return cls(*args)
        return cls(*args, value)


class IdItemsExpr:
    """ID & items expression."""

    def __init__(self, ii_expr_strs: Sequence[str], id_filter_ok: bool) -> None:
        """Initialize."""
        assert len(ii_expr_strs) >= 1
        try:
            self._id_expr = NameValueExpr(ii_expr_strs[0], filter_ok=id_filter_ok)
        except NameValueExprError as exc:
            raise NameValueExprError(f"id: {exc}") from exc
        self._item_exprs = NameValueExprs(ii_expr_strs[1:])

    def __repr__(self) -> str:
        """Return representation string."""
        return (
            f"{self.__class__.__name__}"
            f"(id_value={self._id_expr!r}, items={self._item_exprs!r})"
        )

    @property
    def has_items(self) -> bool:
        """Return if object has item expressions."""
        return bool(self._item_exprs)

    def matching_ids(self, all_ids: Iterable[str]) -> OrderedSet[str]:
        """Return matching IDs."""
        return self._id_expr.matching_names(all_ids)

    def matching_item_names(self, id: str, all_names: Iterable[str]) -> OrderedSet[str]:
        """Return matching item names."""
        if not self._id_expr.name_matches(id):
            return OrderedSet()
        return self._item_exprs.matching_names(all_names)

    def filter_row(self, row: Row) -> tuple[bool, Items]:
        """
        Return if row meets matching criteria,
        and items whose names match item expressions.
        """
        if not self._id_expr.item_matches(row.id, row.value):
            return False, {}

        return self._item_exprs.filter_items(row.items)


class IdItemsExprs(list[IdItemsExpr]):
    """Multiple ID & items expressions."""

    @property
    def has_items(self) -> bool:
        """Return if any ID & items expression has items."""
        return any(ii_expr.has_items for ii_expr in self)

    def matching_ids(self, all_ids: Iterable[str]) -> OrderedSet[str]:
        """Return matching IDs."""
        sets = [ii_expr.matching_ids(all_ids) for ii_expr in self]
        if not sets:
            return OrderedSet()
        return OrderedSet.union(*sets)

    def matching_item_names(self, id: str, all_names: Iterable[str]) -> OrderedSet[str]:
        """Return matching item names."""
        sets = [ii_expr.matching_item_names(id, all_names) for ii_expr in self]
        if not sets:
            return OrderedSet()
        return OrderedSet.union(*sets)

    def filter_row(
        self, row: Row, global_item_exprs: NameValueExprs
    ) -> tuple[bool, Items, Items]:
        """
        Return if row meets matching criteria of any IdItemsExpr/global_items_exprs,
        and items whose names match global expressions
        and those whose names match any item expressions (but not global expressions).
        """
        global_match, global_items = global_item_exprs.filter_items(row.items)
        any_matches = False
        all_self_items = {}
        for ii_expr in self:
            matches, self_items = ii_expr.filter_row(row)
            any_matches |= matches and global_match
            all_self_items |= self_items
        self_items = {k: v for k, v in all_self_items.items() if k not in global_items}
        return any_matches, self_items, global_items


@dataclass(init=False)
class ArgsNamespace:
    """Namespace for arguments."""

    state_exprs: IdItemsExprs
    global_attr_exprs: NameValueExprs

    event_exprs: IdItemsExprs
    core_event_types: bool
    lowercase_event_types: bool
    uppercase_event_types: bool

    start: dt.datetime | None
    start_days_ago: int | None
    start_stops_ago: int | None
    start_beginning: bool

    end: dt.datetime | None
    end_days_ago: int | None
    end_stops_ago: int | None

    time_window: dt.timedelta | None

    dbpath: str
    all_states: bool


@dataclass
class Params:
    """Program parameters."""

    start_specified: bool
    end_specified: bool
    window_specified: bool


def process_args(args: ArgsNamespace, params: Params) -> int:
    """Process arguments."""

    def days_ago(days: int) -> dt.datetime:
        """Return start of number of days ago."""
        start_of_today = today_at()
        return start_of_today - dt.timedelta(days)

    if args.start_days_ago is not None:
        args.start = days_ago(args.start_days_ago)
    elif args.start_stops_ago is not None:
        args.start = find_stop(args.start_stops_ago)

    if args.end_days_ago is not None:
        args.end = days_ago(args.end_days_ago)
    elif args.end_stops_ago is not None:
        args.end = find_stop(args.end_stops_ago)
        if args.end is None:
            print_msg(f"argument -ES: could not find {args.end_stops_ago} stops")
            return 1

    if params.window_specified:
        if params.start_specified and args.start is None:
            args.start = find_oldest()
        if args.start is not None:
            args.end = args.start + args.time_window
        elif args.end is not None:
            args.start = args.end - args.time_window
        else:
            args.start = dt.datetime.now() - args.time_window
    elif not params.start_specified and not params.end_specified:
        args.start = days_ago(0)

    if args.start is not None and args.end is not None and args.start > args.end:
        print_msg(f"start ({args.start}) must not be after end ({args.end})")
        return 2

    return 0


def print_banner(args: ArgsNamespace) -> None:
    """Print banner."""
    cprint(f"Schema version: {get_schema_version()}", COLOR_BANNER)
    if args.start is None:
        start_str = f"beginning ({find_oldest()})"
    else:
        start_str = args.start
    end_str = args.end if args.end is not None else "end (now)"
    cprint(f"Showing from {start_str} to {end_str}", COLOR_BANNER)


@dataclass
class StateQueryResult:
    """State query result."""

    last_updated_ts: float
    entity_id: str
    shared_attrs: str
    state: str | None
    old_state_id: int | None

    def as_row_dict(self) -> dict[str, Any]:
        """Return as dict to be used for Row.from_db_values arguments."""
        return {
            "ts": self.last_updated_ts,
            "id": self.entity_id,
            "items": self.shared_attrs,
            "value": self.state,
        }


TRawState = TypeVar("TRawState", bound="RawState")


class RawState(Row):
    """Raw state."""

    def __init__(
        self,
        last_updated: dt.datetime,
        entity_id: str,
        attributes: Items,
        state: str | None = None,
    ) -> None:
        """Initialize."""
        super().__init__(last_updated, entity_id, attributes, state)

    def __repr__(self) -> str:
        """Return representation string."""
        s = ", ".join(
            [
                str(getattr(self, attr))
                for attr in ["last_updated", "entity_id", "state", "attributes"]
            ]
        )
        return f"{self.__class__.__name__} ({s})"

    @classmethod
    def _from_query(cls: type[TRawState], result: StateQueryResult) -> TRawState:
        """Create object from query result."""
        return cls.from_db_values(**result.as_row_dict())

    @classmethod
    def from_queries(
        cls: type[TRawState], results: Iterable[StateQueryResult]
    ) -> Generator[TRawState, None, None]:
        """Create object from query result."""
        for result in results:
            yield cls._from_query(result)

    @property
    def last_updated(self) -> dt.datetime:
        """Return when last updated."""
        return self.ts

    @property
    def entity_id(self) -> str:
        """Return entity ID."""
        return self.id

    @property
    def attributes(self) -> Items:
        """Return attributes."""
        return self.items

    @property
    def state(self) -> str | None:
        """Return state."""
        return self.value


class State(RawState):
    """State."""

    def __init__(
        self,
        last_updated: dt.datetime,
        entity_id: str,
        attributes: Items,
        state: str | None,
        global_attrs: Items,
    ) -> None:
        """Initialize."""
        super().__init__(last_updated, entity_id, attributes, state)
        self.global_attrs = global_attrs

    def __repr__(self) -> str:
        """Return representation string."""
        s = ", ".join(
            [
                str(getattr(self, attr))
                for attr in [
                    "last_updated",
                    "entity_id",
                    "state",
                    "attributes",
                    "global_attrs",
                ]
            ]
        )
        return f"{self.__class__.__name__} ({s})"


def get_states(
    args: ArgsNamespace,
) -> tuple[OrderedSet[str], OrderedSet[str], list[State], list[State]]:
    """Get states."""
    entity_ids = args.state_exprs.matching_ids(get_unique("entity_id", "states"))
    global_attr_names = args.global_attr_exprs.all_str_names
    if not entity_ids:
        return entity_ids, global_attr_names, [], []

    if args.state_exprs.has_items or args.global_attr_exprs:
        shared_attrs_str = "shared_attrs"
        join_str = (
            "INNER JOIN state_attributes AS a ON s.attributes_id = a.attributes_id"
        )
    else:
        shared_attrs_str = "'{}'"
        join_str = ""
    results = [
        StateQueryResult(*result)
        for result in cast(
            list[tuple[float, str, str, str | None, int | None]],
            con.execute(
                "SELECT last_updated_ts AS ts, entity_id AS key"
                f", {shared_attrs_str}, state, old_state_id"
                " FROM states AS s"
                f" {join_str}"
                f" {where(entity_ids, args.start, args.end)}"
                " ORDER BY ts"
            ).fetchall(),
        )
    ]

    def filter_states(
        state_exprs: IdItemsExprs,
        global_attr_exprs: NameValueExprs,
        raw_states: Iterable[RawState],
    ) -> Generator[State, None, None]:
        for raw_state in raw_states:
            matches, attributes, global_attrs = state_exprs.filter_row(
                raw_state, global_attr_exprs
            )
            if matches:
                yield State(
                    raw_state.last_updated,
                    raw_state.entity_id,
                    attributes,
                    raw_state.state,
                    global_attrs,
                )

    states = list(
        filter_states(
            args.state_exprs, args.global_attr_exprs, RawState.from_queries(results)
        )
    )

    prev_states: list[State] = []
    if len(states) == len(results) and args.start is not None:

        def get_prev_raw_states() -> Generator[RawState, None, None]:
            """Get previous states in raw form."""

            prev_state_base_cmd = (
                "SELECT last_updated_ts AS ts, entity_id AS key"
                f", {shared_attrs_str}, state"
                " FROM states AS s"
                f" {join_str}"
            )
            not_found_entity_ids = list(entity_ids)

            for entity_id in entity_ids:
                old_state_id: int | None = None
                for result in results:
                    if result.entity_id == entity_id:
                        old_state_id = result.old_state_id
                        break
                if old_state_id is None:
                    continue

                yield RawState.from_db_values(
                    *cast(
                        tuple[float, str, str, str | None],
                        con.execute(
                            prev_state_base_cmd + f" WHERE state_id = {old_state_id}"
                        ).fetchone(),
                    )
                )

                not_found_entity_ids.remove(entity_id)

            for entity_id in not_found_entity_ids:
                raw_result = cast(
                    tuple[float, str, str, str | None],
                    con.execute(
                        prev_state_base_cmd + f" {where([entity_id], end=args.start)}"
                        " ORDER BY ts DESC LIMIT 1"
                    ).fetchone(),
                )
                if raw_result:
                    yield RawState.from_db_values(*raw_result)

        def convert_prev_states(
            state_exprs: IdItemsExprs,
            raw_states: Iterable[RawState],
        ) -> Generator[State, None, None]:
            """Convert RawState objects to State objects."""
            for raw_state in raw_states:
                attrs = raw_state.attributes
                attr_names = (
                    state_exprs.matching_item_names(raw_state.entity_id, attrs)
                    - global_attr_names
                )
                yield State(
                    raw_state.last_updated,
                    raw_state.entity_id,
                    {name: attrs.get(name, MISSING) for name in attr_names},
                    raw_state.state,
                    {name: attrs.get(name, MISSING) for name in global_attr_names},
                )

        prev_states = sorted(
            convert_prev_states(args.state_exprs, get_prev_raw_states()),
            key=lambda state: state.last_updated,
        )

    return entity_ids, global_attr_names, prev_states, states


class Event(Row):
    """Event."""

    def __init__(self, time_fired: dt.datetime, type: str, data: Items) -> None:
        super().__init__(time_fired, type, data)

    @property
    def time_fired(self) -> dt.datetime:
        """Return when fired."""
        return self.ts

    @property
    def type(self) -> str:
        """Return event type."""
        return self.id

    @property
    def data(self) -> Items:
        """Return event data."""
        return self.items


def get_events(args: ArgsNamespace) -> list[Event]:
    """Get events."""
    all_event_types = get_unique("event_type", "events")
    event_types = args.event_exprs.matching_ids(all_event_types)
    if args.core_event_types:
        event_types.update(CORE_EVENTS)
    if args.uppercase_event_types:
        event_types.update(filter(lambda etype: etype.isupper(), all_event_types))
    if args.lowercase_event_types:
        event_types.update(filter(lambda etype: etype.islower(), all_event_types))
    if not event_types:
        return []

    if args.event_exprs.has_items:
        shared_data_str = "shared_data"
        join_str = "LEFT JOIN event_data AS d ON e.data_id = d.data_id"
    else:
        shared_data_str = "'{}'"
        join_str = ""
    return [
        Event.from_db_values(*result)
        for result in cast(
            list[tuple[float, str, str]],
            con.execute(
                "SELECT time_fired_ts AS ts, event_type AS key"
                f", {shared_data_str}"
                " FROM events AS e"
                f" {join_str}"
                f" {where(event_types, args.start, args.end)}"
                " ORDER BY ts"
            ).fetchall(),
        )
    ]


StateAttrs = tuple[str | None, Items, Items]


class Printer:
    """State & event printer."""

    _col_1_width: int
    _state_width: int
    _attr_fields: list[tuple[str, int]]
    _row_sep: str | None = None

    _ts_idx: int = -1
    _ts_color: str
    _ts_last_date: dt.date | None = None

    _prev_state_attrs: dict[str, StateAttrs | None]
    _state_color: dict[str, str]
    _state_printed: bool = False
    _prev_entity_id: str | None = None

    def __init__(
        self,
        args: ArgsNamespace,
        entity_ids: OrderedSet[str],
        global_attr_names: Iterable[str],
        prev_states: Sequence[State],
        states: Sequence[State],
        events: Sequence[Event],
    ) -> None:
        """Initialize printer."""

        self._start = args.start
        self._all_states = args.all_states
        self._entity_ids = entity_ids
        self._global_attr_names = global_attr_names
        self._other_attrs = any(state.attributes for state in states)
        self._prev_states = prev_states
        self._states = states
        self._events = events

        if prev_states:
            assert self._start is not None
            last_prev_state_ts = prev_states[-1].ts
            assert last_prev_state_ts < self._start
            if states:
                assert last_prev_state_ts < states[0].ts
            if events:
                assert last_prev_state_ts < events[0].ts

    def print(self) -> None:
        """Print header, states & events."""
        self._print_hdr()
        self._print_sep_row()

        if not self._prev_states and not self._states and not self._events:
            return

        self._prev_state_attrs = cast(
            dict[str, StateAttrs | None], dict.fromkeys(self._entity_ids)
        )
        seen_entity_ids = set([state.entity_id for state in self._states]) | set(
            [state.entity_id for state in self._prev_states]
        )
        self._state_color = dict(
            zip(self._entity_ids & seen_entity_ids, cycle(COLORS_STATES)),
        )

        if self._prev_states:
            for prev_state in self._prev_states:
                self._print_state_row(prev_state)
            self._print_sep_row()
            self._prev_entity_id = None

        for row in sorted(
            cast(Sequence[State | Event], self._states + self._events),
            key=lambda row: row.ts,
        ):
            if isinstance(row, State):
                self._print_state_row(row)
            else:
                self._print_event_row(row)

    def _print_hdr(self) -> None:
        """Print header."""
        self._col_1_width = max(
            max(map(lambda state: len(state.entity_id), self._prev_states), default=0),
            max(map(lambda state: len(state.entity_id), self._states), default=0),
            max(map(lambda event: len(event.type) + 6, self._events), default=0),
            len(COL1_HEADER),
        )

        if self._prev_states or self._states:
            self._state_width = max(
                max(
                    map(lambda state: len(str(state.state)), self._prev_states),
                    default=0,
                ),
                max(map(lambda state: len(str(state.state)), self._states), default=0),
                len(STATE_HEADER),
            )
            state_hdr = [STATE_HEADER.center(self._state_width)]
            attr_field_func = self._attr_field_w_states
        else:
            self._state_width = 0
            state_hdr = []
            attr_field_func = lambda name: (name, len(name))

        self._attr_fields = list(map(attr_field_func, self._global_attr_names))
        attr_hdrs = [name.center(width) for name, width in self._attr_fields]

        if self._other_attrs:
            attr_hdrs.append(ATTRS_HEADER)
        print(
            COL1_HEADER.center(self._col_1_width),
            TS_HEADER.center(TS_WIDTH),
            *state_hdr,
            *attr_hdrs,
            sep=COL_SEP,
        )

    def _attr_field_w_states(self, name: str) -> tuple[str, int]:
        """Return field parameters for global attr using values from states."""
        width = max(
            max(
                map(
                    lambda state: len(str(state.global_attrs.get(name, MISSING))),
                    self._prev_states,
                ),
                default=0,
            ),
            max(
                map(
                    lambda state: len(str(state.global_attrs.get(name, MISSING))),
                    self._states,
                ),
                default=0,
            ),
            len(name),
        )
        return name, width

    def _print_sep_row(self) -> None:
        """Print separation row."""
        if not self._row_sep:
            state_hdr = (
                ["-" * self._state_width] if self._prev_states or self._states else []
            )
            attr_hdrs = ["-" * attr_len for _, attr_len in self._attr_fields]
            self._row_sep = HDR_SEP.join(
                ["-" * self._col_1_width, "-" * TS_WIDTH] + state_hdr + attr_hdrs
            )
            if self._other_attrs:
                self._row_sep += HDR_SEP
                self._row_sep += "-" * (
                    get_terminal_size().columns - len(self._row_sep)
                )
        print(self._row_sep)

    def _print_state_row(self, state: State) -> None:
        """Print state row."""
        entity_id = state.entity_id
        state_attrs = state.state, state.global_attrs, state.attributes
        if not self._all_states and state_attrs == self._prev_state_attrs[entity_id]:
            return

        if entity_id != self._prev_entity_id:
            entity_id_str = entity_id
        else:
            entity_id_str = ""
        color = self._state_color[entity_id]
        _attrs = [
            colored(str(state.global_attrs.get(name, MISSING)).ljust(width), color)
            for name, width in self._attr_fields
        ]
        if self._other_attrs:
            _attrs.append(
                colored(
                    ", ".join(f"{k}={v}" for k, v in state.attributes.items()), color
                )
            )
        ts_str, sep = self._ts_str_sep(state.ts)
        print(
            colored(entity_id_str.ljust(self._col_1_width), color),
            ts_str,
            colored(str(state.state).ljust(self._state_width), color),
            *_attrs,
            sep=sep,
        )
        self._state_printed = True
        if not self._all_states:
            self._prev_state_attrs[entity_id] = state_attrs
        self._prev_entity_id = entity_id

    def _print_event_row(self, event: Event) -> None:
        """Print event row."""
        event_str = f" {event.type} "
        if event.type in CORE_EVENTS:
            if event.type == "homeassistant_stop":
                fill = "#"
                colors = COLORS_STOP
            else:
                fill = "="
                colors = COLORS_HA_EVENT
        else:
            fill = "-"
            colors = COLORS_USER_EVENT

        ts_str, sep = self._ts_str_sep(event.ts)

        print(
            colored(event_str.center(self._col_1_width, fill), *colors),
            ts_str,
            ", ".join([f"{k}={v}" for k, v in event.data.items()]),
            sep=sep,
        )

        self._prev_entity_id = None

    def _ts_str_sep(self, row_ts: dt.datetime) -> tuple[str, str]:
        """Return row timestamp & separator strings."""
        row_date = row_ts.date()
        if row_date != self._ts_last_date:
            self._ts_idx += 1
            self._ts_color = COLORS_TS[self._ts_idx % len(COLORS_TS)]
            self._ts_last_date = row_date
        return colored(row_ts, self._ts_color), colored(COL_SEP, self._ts_color)


def main(args: ArgsNamespace, params: Params) -> str | int | None:
    """Print requested events and/or states."""
    global con

    con = sqlite3.connect(Path(args.dbpath).expanduser().resolve())

    try:
        if err := process_args(args, params):
            return err

        print_banner(args)

        entity_ids, global_attr_names, prev_states, states = get_states(args)
        events = get_events(args)

    finally:
        con.close()

    Printer(args, entity_ids, global_attr_names, prev_states, states, events).print()


class ArgError(Exception):
    """Argument error."""


class IdItemsExprsAction(argparse.Action):
    """Action to store ID/value & items expressions."""

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: ArgsNamespace,
        values: list[str],
        option_string: str | None = None,
    ) -> None:
        """Process ID/value & items expressions argument."""
        try:
            exprs = IdItemsExpr(values, id_filter_ok=option_string == "-s")
        except NameValueExprError as exc:
            raise ArgError(f"{option_string} argument: {exc}") from exc
        cast(IdItemsExprs, getattr(namespace, self.dest)).append(exprs)


class NameValueExprAction(argparse.Action):
    """Action to store name/value expressions."""

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: ArgsNamespace,
        values: list[str],
        option_string: str | None = None,
    ) -> None:
        """Process name/value expressions argument."""
        try:
            exprs = NameValueExprs(values, name_regex_ok=False)
        except NameValueExprError as exc:
            raise ArgError(f"{option_string} argument: {exc}") from exc
        cast(NameValueExprs, getattr(namespace, self.dest)).extend(exprs)


def parse_args() -> tuple[ArgsNamespace, Params]:
    """Parse command line arguments."""
    global print_usage

    parser = argparse.ArgumentParser(
        description="Retrieve states and/or events from HA database"
    )
    print_usage = parser.print_usage

    parser.add_argument(
        "-d",
        default=DEF_DATABASE,
        help=f"database path (default: {DEF_DATABASE})",
        dest="dbpath",
    )

    # states

    state_group = parser.add_argument_group("states", "Entity IDs & attributes")
    state_group.add_argument(
        "-s",
        action=IdItemsExprsAction,
        nargs="+",
        default=IdItemsExprs(),
        help="entity ID/state & optional attribute expressions ([%%]NAME[=[%%]VALUE])",
        metavar=("ID_STATE_EXPR", "ATTR_EXPR"),
        dest="state_exprs",
    )
    state_group.add_argument(
        "-a",
        action=NameValueExprAction,
        nargs="+",
        default=NameValueExprs(name_regex_ok=False),
        help="global attribute expressions",
        metavar="ATTR_EXPR",
        dest="global_attr_exprs",
    )
    state_group.add_argument(
        "-A",
        action="store_true",
        help="show all states (not just unique ones)",
        dest="all_states",
    )

    # events

    event_group = parser.add_argument_group("events", "Event types")
    event_group.add_argument(
        "-e",
        action=IdItemsExprsAction,
        nargs="+",
        default=IdItemsExprs(),
        help="event type ([%%]NAME) & optional data ([%%]NAME[=[%%]VALUE]) expressions",
        metavar=("TYPE_EXPR", "DATA_EXPR"),
        dest="event_exprs",
    )
    event_group.add_argument(
        "-c",
        action="store_true",
        help="show all HA core events",
        dest="core_event_types",
    )
    event_group.add_argument(
        "-l",
        action="store_true",
        help="show all lowercase/system event types",
        dest="lowercase_event_types",
    )
    event_group.add_argument(
        "-u",
        action="store_true",
        help="show all uppercase/user event types",
        dest="uppercase_event_types",
    )

    # time

    time_group = parser.add_argument_group(
        "time",
        "Time window. Can specify up to 2 of start, end & window."
        " Default is today (-SD 0).",
    )
    start_group = time_group.add_mutually_exclusive_group()
    start_group.add_argument(
        "-S",
        help="start at DATETIME, DATE or TIME",
        metavar="DATETIME",
        dest="start",
    )
    start_group.add_argument(
        "-SD", type=int, help="start DAYS ago", metavar="DAYS", dest="start_days_ago"
    )
    start_group.add_argument(
        "-SS", type=int, help="start STOPS ago", metavar="STOPS", dest="start_stops_ago"
    )
    start_group.add_argument(
        "-SB",
        action="store_true",
        help="start at beginning",
        dest="start_beginning",
    )
    end_group = time_group.add_mutually_exclusive_group()
    end_group.add_argument(
        "-E",
        help="end at DATETIME, DATE or TIME",
        metavar="DATETIME",
        dest="end",
    )
    end_group.add_argument(
        "-ED", type=int, help="end DAYS ago", metavar="DAYS", dest="end_days_ago"
    )
    end_group.add_argument(
        "-ES", type=int, help="end STOPS ago", metavar="STOPS", dest="end_stops_ago"
    )
    time_group.add_argument(
        "-W",
        type=float,
        help="time window in days",
        metavar="DAYS",
        dest="time_window",
    )

    def datetime_arg(opt: str, arg: str) -> dt.datetime:
        """Convert argument string to datetime."""
        with suppress(ValueError):
            return today_at(dt.time.fromisoformat(arg))
        try:
            return dt.datetime.fromisoformat(arg)
        except ValueError as exc:
            raise ArgError(f"argument {opt}: {exc}") from exc

    try:
        args = parser.parse_args(namespace=ArgsNamespace())

        if args.start is not None:
            args.start = datetime_arg("-S", args.start)
        if args.start_days_ago is not None and args.start_days_ago < 0:
            raise ArgError(f"argument -SD: must be >= 0: {args.start_days_ago}")
        if args.start_stops_ago is not None and args.start_stops_ago <= 0:
            raise ArgError(f"argument -SS: must be > 0: {args.start_stops_ago}")
        if args.end is not None:
            args.end = datetime_arg("-E", args.end)
        if args.end_days_ago is not None and args.end_days_ago < 0:
            raise ArgError(f"argument -ED: must be >= 0: {args.end_days_ago}")
        if args.end_stops_ago is not None and args.end_stops_ago <= 0:
            raise ArgError(f"argument -ES: must be > 0: {args.end_stops_ago}")
        if args.time_window is not None:
            if args.time_window <= 0:
                raise ArgError(f"argument -W: must be > 0: {args.time_window}")
            args.time_window = dt.timedelta(args.time_window)

        start_specified = (
            args.start is not None
            or args.start_days_ago is not None
            or args.start_stops_ago is not None
            or args.start_beginning
        )
        end_specified = (
            args.end is not None
            or args.end_days_ago is not None
            or args.end_stops_ago is not None
        )
        window_specified = args.time_window is not None

        if sum([start_specified, end_specified, window_specified]) > 2:
            raise ArgError("can only specify at most 2 of start, end & window")

    except ArgError as exc:
        print_msg(exc)
        sys.exit(2)

    return args, Params(start_specified, end_specified, window_specified)


if __name__ == "__main__":
    args, params = parse_args()
    sys.exit(main(args, params))
