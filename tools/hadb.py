#!/usr/bin/env python3
from __future__ import annotations

import argparse
from collections.abc import Callable, Iterable, Sequence
from contextlib import suppress
from dataclasses import dataclass, field
import datetime as dt
import json
from os.path import basename
from pathlib import Path
import re
from shutil import get_terminal_size
import sqlite3
import sys
from typing import Any, TypeVar, cast

from termcolor import colored, cprint


DEF_DATABASE = "~/homeassistant/production/config/home-assistant_v2.db"
CORE_EVENTS = [
    "homeassistant_start",
    "homeassistant_started",
    "homeassistant_stop",
    "core_config_updated",
]
COL1_HEADER = "entity_id / event_type"
STATE_HEADER = "state"
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


def find_oldest() -> dt.datetime:
    """Find oldest event or state update."""

    def get_oldest(table: str, column: str) -> dt.datetime:
        """Get oldest time."""
        return dt.datetime.fromtimestamp(
            con.execute(
                "SELECT {column} FROM {table} ORDER BY {column} LIMIT 1".format(
                    table=table,
                    column=column,
                )
            ).fetchone()[0]
        )

    oldest_state_update = get_oldest("states", "last_updated_ts")
    oldest_event = get_oldest("events", "time_fired_ts")
    return min(oldest_state_update, oldest_event)


def where(
    keys: list[str],
    start: dt.datetime | None = None,
    end: dt.datetime | None = None,
) -> str:
    """Create WHERE clause."""
    result: list[str] = []
    if len(keys) == 1:
        result.append(f"key = '{keys[0]}'")
    elif len(keys) > 1:
        result.append(f"key IN {repr(tuple(keys))}")
    if start is not None:
        result.append(f"ts >= {start.timestamp()}")
    if end is not None:
        result.append(f"ts < {end.timestamp()}")
    return f"WHERE {' AND '.join(result)}" if result else ""


def today_at(time: dt.time = dt.time()) -> dt.datetime:
    """Return datetime for today at specified time or midnight this morning."""
    return dt.datetime.combine(dt.datetime.now().date(), time)


@dataclass(init=False)
class ArgsNamespace:
    """Namespace for arguments."""

    attributes: list[str]
    entity_ids_attrs: dict[str, list[str]]
    entity_ids_attrs_er: dict[str, list[str]]

    event_types: list[str]
    event_types_re: list[str]
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
    schema_version = con.execute(
        "SELECT schema_version FROM schema_changes ORDER BY schema_version DESC LIMIT 1"
    ).fetchone()[0]
    cprint(f"Schema version: {schema_version}", COLOR_BANNER)
    if args.start is None:
        start_str = f"beginning ({find_oldest()})"
    else:
        start_str = args.start
    end_str = args.end if args.end is not None else "end (now)"
    cprint(f"Showing from {start_str} to {end_str}", COLOR_BANNER)


def get_unique(table: str, key: str) -> list[str]:
    """Get all unique keys from table."""
    try:
        return list(
            zip(*con.execute(f"SELECT DISTINCT {key} FROM {table}").fetchall())
        )[0]
    except IndexError:
        return set()


EntityAttrs = dict[str, list[str] | list[re.Pattern[str]]]


def get_entity_ids_and_attributes(args: ArgsNamespace) -> EntityAttrs:
    """Get entity IDs and their associated attributes."""
    entity_attrs: EntityAttrs = {}

    all_entity_ids = get_unique("states", "entity_id")
    for eid, is_regex in StateAction.entries.items():
        if is_regex:
            eid_pat = re.compile(eid)
            attr_pats = [re.compile(attr) for attr in args.entity_ids_attrs_er[eid]]
            for entity_id in all_entity_ids:
                if eid_pat.fullmatch(entity_id):
                    entity_attrs[entity_id] = attr_pats
        else:
            entity_attrs[eid] = args.entity_ids_attrs[eid]

    return entity_attrs


@dataclass
class StateQueryResult:
    """State query result."""

    ts: float
    entity_id: str
    state: str | None
    old_state_id: int | None
    shared_attrs: str


class State:
    """State."""

    def __init__(
        self,
        ts: float,
        entity_id: str,
        state: str | None,
        attrs: str,
    ) -> None:
        """Initialize."""
        self.ts = dt.datetime.fromtimestamp(ts)
        self.entity_id = entity_id
        self.state = state
        self.attributes = cast(dict[str, Any], json.loads(attrs))


def get_states(
    entity_ids: list[str],
    include_attrs: bool = True,
    start: dt.datetime | None = None,
    end: dt.datetime | None = None,
) -> list[State]:
    """Get states."""
    if include_attrs:
        shared_attrs_str = "shared_attrs"
        join_str = (
            "INNER JOIN state_attributes AS a ON s.attributes_id = a.attributes_id"
        )
    else:
        shared_attrs_str = "'{}'"
        join_str = ""
    results = [
        StateQueryResult(*result)
        for result in con.execute(
            "SELECT last_updated_ts AS ts, entity_id AS key, state, old_state_id"
            f", {shared_attrs_str}"
            " FROM states AS s"
            f" {join_str}"
            f" {where(entity_ids, start, end)}"
            " ORDER BY ts"
        ).fetchall()
    ]

    states = [
        State(result.ts, result.entity_id, result.state, result.shared_attrs)
        for result in results
    ]

    if start is not None:
        not_found_entity_ids = entity_ids[:]
        prev_states: list[State] = []

        for entity_id in entity_ids:
            try:
                old_state_id = [
                    result.old_state_id
                    for result in results
                    if result.entity_id == entity_id
                ][0]
            except IndexError:
                continue
            if old_state_id is None:
                continue
            prev_states.append(
                State(
                    *con.execute(
                        "SELECT last_updated_ts, entity_id, state"
                        f", {shared_attrs_str}"
                        " FROM states AS s"
                        f" {join_str}"
                        f" WHERE state_id = {old_state_id}"
                    ).fetchone()
                )
            )
            not_found_entity_ids.remove(entity_id)

        for entity_id in not_found_entity_ids:
            result = con.execute(
                "SELECT last_updated_ts AS ts, entity_id AS key, state"
                f", {shared_attrs_str}"
                " FROM states AS s"
                f" {join_str}"
                f" WHERE key = '{entity_id}' AND ts < {start.timestamp()}"
                " ORDER BY ts DESC LIMIT 1"
            ).fetchone()
            if result:
                prev_states.append(State(*result))

        states = sorted(states + prev_states, key=lambda state: state.ts)

    return states


def get_event_types(args: ArgsNamespace) -> list[str]:
    """Get event types."""
    event_types = args.event_types

    all_event_types = get_unique("events", "event_type")
    for pat in args.event_types_re:
        pat = re.compile(pat)
        event_types.extend(
            [event_type for event_type in all_event_types if pat.fullmatch(event_type)]
        )

    if args.core_event_types:
        event_types.extend(CORE_EVENTS)
    if args.uppercase_event_types:
        event_types.extend(filter(lambda s: s.isupper(), all_event_types))
    if args.lowercase_event_types:
        event_types.extend(filter(lambda s: s.islower(), all_event_types))

    return event_types


@dataclass
class Event:
    """Event"""

    ts: dt.datetime
    type: str
    data: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Make sure data is a dict."""
        self.data = self.data or {}


def get_events(
    event_types: list[str],
    include_data: bool = True,
    start: dt.datetime | None = None,
    end: dt.datetime | None = None,
) -> list[Event]:
    """Get events."""
    events: list[Event] = []

    if include_data:
        cmd = (
            "SELECT time_fired_ts AS ts, event_type AS key, shared_data"
            " FROM events AS e"
            " LEFT JOIN event_data AS d ON e.data_id = d.data_id"
            f" {where(event_types, start, end)}"
            " ORDER BY ts"
        )
        for ts, event_type, shared_data in cast(
            list[tuple[float, str, str | None]], con.execute(cmd).fetchall()
        ):
            if shared_data is not None:
                shared_data = cast(dict[str, Any], json.loads(shared_data))
            events.append(Event(dt.datetime.fromtimestamp(ts), event_type, shared_data))
    else:
        cmd = (
            "SELECT time_fired_ts AS ts, event_type AS key"
            " FROM events"
            f" {where(event_types, start, end)}"
            " ORDER BY ts"
        )
        for ts, event_type in cast(
            list[tuple[float, str]], con.execute(cmd).fetchall()
        ):
            events.append(Event(dt.datetime.fromtimestamp(ts), event_type))

    return events


class Printer:
    """State & event printer."""

    _col_1_width: int
    _max_state_len: int
    _attr_fields: list[tuple[str, int]]
    _row_sep: str | None = None

    _ts_idx: int = -1
    _ts_color: str
    _ts_last_date: dt.date | None = None

    _state_color: dict[str, str]
    _state_printed: bool = False
    _prev_entity_id: str | None = None

    def __init__(
        self,
        args: ArgsNamespace,
        entity_attrs: EntityAttrs,
        states: list[State],
        events: list[Event],
    ) -> None:
        """Initialize printer."""
        self._entity_attrs = entity_attrs
        self._states = states
        self._events = events

        self._start = args.start
        self._attributes = args.attributes
        self._all_states = args.all_states
        self._other_attrs = any(entity_attrs.values())

        self._last_state_attrs = cast(
            dict[str, tuple[str, list[str]] | None],
            dict.fromkeys(entity_attrs),
        )

    def print(self) -> None:
        """Print header, states & events."""
        self._print_hdr()
        self._print_sep_row()

        rows = sorted(self._states + self._events, key=lambda x: x.ts)
        if not rows:
            return

        self._assign_state_colors()
        print_old_states = bool(self._start)
        for row in rows:
            if print_old_states and self._state_printed and row.ts >= self._start:
                print_old_states = False
                self._print_sep_row()
                self._prev_entity_id = None

            if isinstance(row, Event):
                self._print_event_row(row)
                self._prev_entity_id = None
            else:
                self._print_state_row(row)

    def _print_hdr(self) -> None:
        """Print header."""
        self._col_1_width = max(
            max(len(state.entity_id) for state in self._states) if self._states else 0,
            (max(len(event.type) for event in self._events) + 6) if self._events else 0,
            len(COL1_HEADER),
        )

        if self._states:
            self._max_state_len = max(
                *[len(state.state) for state in self._states],
                len(STATE_HEADER),
            )
            state_hdr = [f"{STATE_HEADER:{self._max_state_len}}"]
        else:
            self._max_state_len = 0
            state_hdr = []

        self._attr_fields = [
            (
                attr,
                max(
                    [
                        len(str(state.attributes.get(attr, MISSING)))
                        for state in self._states
                    ] + [len(attr)]
                ),
            )
            for attr in self._attributes
        ]
        attr_hdrs = [f"{attr:{attr_len}}" for attr, attr_len in self._attr_fields]
        if self._other_attrs:
            attr_hdrs.append("attributes")
        print(
            f"{COL1_HEADER:{self._col_1_width}}",
            f"{'last_updated / time_fired':26}",
            *state_hdr,
            *attr_hdrs,
            sep=" | ",
        )

    def _print_sep_row(self) -> None:
        """Print separation row."""
        if not self._row_sep:
            state_hdr = ["-" * self._max_state_len] if self._states else []
            attr_hdrs = ["-" * attr_len for _, attr_len in self._attr_fields]
            self._row_sep = "-|-".join(
                ["-" * self._col_1_width, "-" * 26] + state_hdr + attr_hdrs
            )
            if self._other_attrs:
                self._row_sep += "-|-"
                self._row_sep += "-" * (
                    get_terminal_size().columns - len(self._row_sep)
                )
        print(self._row_sep)

    def _assign_state_colors(self) -> None:
        """Assign state colors."""
        self._state_color = {}
        idx = 0
        for entity_id in self._entity_attrs:
            if entity_id not in self._state_color:
                self._state_color[entity_id] = COLORS_STATES[idx % len(COLORS_STATES)]
                idx += 1

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
            colored(f"{event_str:{fill}^{self._col_1_width}}", *colors),
            ts_str,
            ", ".join([f"{k}: {v}" for k, v in event.data.items()]),
            sep=sep,
        )

    def _print_state_row(self, state: State) -> None:
        """Print state row."""
        if (entity_id := state.entity_id) != self._prev_entity_id:
            entity_id_str = entity_id
        else:
            entity_id_str = ""
        color = self._state_color[entity_id]
        _attrs = [
            colored(f"{state.attributes.get(attr, MISSING):<{attr_len}}", color)
            for attr, attr_len in self._attr_fields
        ]
        if self._other_attrs:
            attr_strs_pats = self._entity_attrs[entity_id]
            if any(
                isinstance(attr_str_pat, re.Pattern)
                for attr_str_pat in attr_strs_pats
            ):
                e_attrs: list[str] = []
                for attr_pat in cast(list[re.Pattern[str]], attr_strs_pats):
                    for attr in state.attributes:
                        if attr not in e_attrs and attr_pat.fullmatch(attr):
                            e_attrs.append(attr)
            elif "*" in cast(list[str], attr_strs_pats):
                e_attrs = list(state.attributes)
            else:
                e_attrs = cast(list[str], attr_strs_pats)
            _attrs.append(
                colored(
                    ", ".join(
                        f"{e_attr}={state.attributes.get(e_attr, MISSING)}"
                        for e_attr in e_attrs
                    ),
                    color,
                )
            )
        state_attrs = (state.state, _attrs)
        if not self._all_states and state_attrs == self._last_state_attrs[entity_id]:
            return
        ts_str, sep = self._ts_str_sep(state.ts)
        print(
            colored(f"{entity_id_str:{self._col_1_width}}", color),
            ts_str,
            colored(f"{state.state:{self._max_state_len}}", color),
            *_attrs,
            sep=sep,
        )
        self._state_printed = True
        if not self._all_states:
            self._last_state_attrs[entity_id] = state_attrs
        self._prev_entity_id = entity_id

    def _ts_str_sep(self, row_ts: dt.datetime) -> tuple[str, str]:
        """Return row timestamp & separator strings."""
        row_date = row_ts.date()
        if row_date != self._ts_last_date:
            self._ts_idx += 1
            self._ts_color = COLORS_TS[self._ts_idx % len(COLORS_TS)]
            self._ts_last_date = row_date
        return colored(row_ts, self._ts_color), colored(" | ", self._ts_color)


def main(args: ArgsNamespace, params: Params) -> str | int | None:
    """Print requested events and/or states."""
    global con

    con = sqlite3.connect(Path(args.dbpath).expanduser().resolve())

    try:
        if err := process_args(args, params):
            return err

        print_banner(args)

        entity_attrs = get_entity_ids_and_attributes(args)
        if entity_attrs:
            states = get_states(
                list(entity_attrs),
                include_attrs=any(entity_attrs.values()) or bool(args.attributes),
                start=args.start,
                end=args.end,
            )
        else:
            states = []
        queried_entity_ids = set(entity_attrs)
        found_entity_ids = set(state.entity_id for state in states)
        if found_entity_ids != queried_entity_ids:
            print_msg(
                "states not found for: "
                f"{', '.join(queried_entity_ids - found_entity_ids)}",
                color="light_yellow",
                prefix="NOTE",
                usage=False,
            )

        event_types = get_event_types(args)
        if event_types:
            events = get_events(event_types, start=args.start, end=args.end)
        else:
            events = []
        queried_event_types = set(event_types)
        found_event_types = set(event.type for event in events)
        if found_event_types != queried_event_types:
            print_msg(
                "events not found for: "
                f"{', '.join(queried_event_types - found_event_types)}",
                color="light_yellow",
                prefix="NOTE",
                usage=False,
            )

    finally:
        con.close()

    Printer(args, entity_attrs, states, events).print()


class ArgError(Exception):
    """Argument error."""


class StateAction(argparse.Action):
    """Action to store state entity IDs & attributes."""

    entries: dict[str, bool] = {}

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: ArgsNamespace,
        values: list[str],
        option_string: str | None = None,
    ) -> None:
        """Process state entity ID & attributes argument."""
        entity_id = values[0]
        attrs = values[1:]
        is_regex=self.dest.endswith("_er")
        self.__class__.entries[entity_id] = is_regex
        cast(dict[str, list[str]], getattr(namespace, self.dest))[entity_id] = attrs


def parse_args() -> tuple[ArgsNamespace, Params]:
    """Parse command line arguments."""
    global print_usage

    parser = argparse.ArgumentParser(
        description="Retrieve states and/or events from HA database"
    )
    print_usage = parser.print_usage

    # states

    state_group = parser.add_argument_group("states", "Entity IDs & attributes")
    state_group.add_argument(
        "-a",
        action="extend",
        nargs="+",
        default=[],
        help="global attributes",
        metavar="ATTR",
        dest="attributes",
    )
    state_group.add_argument(
        "-s",
        action=StateAction,
        nargs="+",
        default={},
        help='entity ID & optional attributes; ATTR may be "*" for all attributes',
        metavar=("ID", "ATTR"),
        dest="entity_ids_attrs",
    )
    state_group.add_argument(
        "-sr",
        action=StateAction,
        nargs="+",
        default={},
        help="regular expressions for entity ID & optional attributes",
        metavar=("ID_RE", "ATTR_RE"),
        dest="entity_ids_attrs_er",
    )

    # events

    event_group = parser.add_argument_group("events", "Event types")
    event_group.add_argument(
        "-e",
        action="extend",
        nargs="+",
        default=[],
        help="event types",
        metavar="TYPE",
        dest="event_types",
    )
    event_group.add_argument(
        "-er",
        action="extend",
        nargs="+",
        default=[],
        help="regular expressions for event type",
        metavar="TYPE_RE",
        dest="event_types_re",
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
        "Time window. Can specify up to 2 of start, end & window. Default is today.",
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

    parser.add_argument(
        "-d",
        default=DEF_DATABASE,
        help=f"database path (default: {DEF_DATABASE})",
        dest="dbpath",
    )
    parser.add_argument(
        "-A",
        action="store_true",
        help="show all states (not just unique ones)",
        dest="all_states",
    )

    args = parser.parse_args(namespace=ArgsNamespace())

    def datetime_arg(opt: str, arg: str) -> dt.datetime:
        """Convert argument string to datetime."""
        with suppress(ValueError):
            return today_at(dt.time.fromisoformat(arg))
        try:
            return dt.datetime.fromisoformat(arg)
        except ValueError as exc:
            raise ArgError(f"argument {opt}: {exc}")

    try:
        for entity_id in args.entity_ids_attrs:
            if entity_id.count(".") != 1:
                raise ArgError(
                    f"first argument -s: must be domain.object_id: '{entity_id}'"
                )

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
