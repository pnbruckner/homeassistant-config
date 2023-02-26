#!/usr/bin/env python3
from __future__ import annotations

import argparse
from collections.abc import Sequence
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
from typing import Any, cast

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


def print_error(*args: Any, **kwargs: Any) -> None:
    """Print error message to stderr."""
    print_usage(file=sys.stderr)
    print(f"{basename(sys.argv[0])}: error:", *args, **kwargs, file=sys.stderr)


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
    keys: Sequence[str],
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

    dbpath: str

    attributes: list[str]
    entity_ids_attrs: list[list[str]]
    entity_ids_attrs_re: list[list[str]]

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
            print_error(f"argument -ES: could not find {args.end_stops_ago} stops")
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
        print_error(f"start ({args.start}) must not be after end ({args.end})")
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


def get_all(table: str, key: str, ts: str, args: ArgsNamespace) -> set[str]:
    """Get all entity IDs."""
    return {
        value[0]
        for value in con.execute(
            f"SELECT {key} AS key, {ts} AS ts FROM {table}"
            f" {where([], args.start, args.end)} GROUP BY key"
        ).fetchall()
    }


EntityAttrs = dict[str, list[str] | list[re.Pattern[str]]]


def get_entity_ids_and_attributes(
    args: ArgsNamespace, all_entity_ids: set[str]
) -> tuple[EntityAttrs, int]:
    """Get entity IDs and their associated attributes."""
    max_entity_id_len = 0
    entity_attrs: EntityAttrs = {}

    for values in args.entity_ids_attrs:
        entity_id = values[0]
        attrs = values[1:]
        entity_attrs[entity_id] = attrs
        if (entity_id_len := len(entity_id)) > max_entity_id_len:
            max_entity_id_len = entity_id_len

    for regexs in args.entity_ids_attrs_re:
        eid_pat = re.compile(regexs[0])
        attr_pats = [re.compile(regex) for regex in regexs[1:]]
        for entity_id in all_entity_ids:
            if not eid_pat.fullmatch(entity_id):
                continue
            entity_attrs[entity_id] = attr_pats
            if (entity_id_len := len(entity_id)) > max_entity_id_len:
                max_entity_id_len = entity_id_len

    return entity_attrs, max_entity_id_len


@dataclass
class State:
    """State"""

    ts: dt.datetime
    entity_id: str
    state: str | None
    attributes: dict[str, Any] = field(default_factory=dict)


def get_states(
    entity_ids: Sequence[str],
    include_attrs: bool = True,
    start: dt.datetime | None = None,
    end: dt.datetime | None = None,
) -> list[State]:
    """Get states."""
    states: list[State] = []

    if include_attrs:
        cmd = (
            "SELECT last_updated_ts AS ts, entity_id AS key, state, shared_attrs"
            " FROM states AS s"
            " INNER JOIN state_attributes AS a ON s.attributes_id = a.attributes_id"
            f" {where(entity_ids, start, end)}"
            " ORDER BY ts"
        )
        for ts, entity_id, state, shared_attrs in cast(
            list[tuple[float, str | None, str]], con.execute(cmd).fetchall()
        ):
            shared_attrs = cast(dict[str, Any], json.loads(shared_attrs))
            states.append(
                State(dt.datetime.fromtimestamp(ts), entity_id, state, shared_attrs)
            )
    else:
        cmd = (
            "SELECT last_updated_ts AS ts, entity_id AS key, state"
            " FROM states"
            f" {where(entity_ids, start, end)}"
            " ORDER BY ts"
        )
        for ts, entity_id, state in cast(
            list[tuple[float, str | None]], con.execute(cmd).fetchall()
        ):
            states.append(
                State(dt.datetime.fromtimestamp(ts), entity_id, state)
            )

    return states


def get_event_types(
    args: ArgsNamespace, all_event_types: set[str]
) -> tuple[list[str], int]:
    """Get event types."""
    event_types = args.event_types

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

    if event_types:
        max_event_type_len = max(len(event_type) for event_type in event_types) + 6
    else:
        max_event_type_len = 0

    return event_types, max_event_type_len


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
    event_types: Sequence[str],
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
            events.append(
                Event(dt.datetime.fromtimestamp(ts), event_type, shared_data)
            )
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
            events.append(
                Event(dt.datetime.fromtimestamp(ts), event_type)
            )

    return events


def print_results(
    entity_attrs: EntityAttrs,
    attributes: list[str],
    max_entity_id_len: int,
    states: list[State],
    max_state_len: int,
    max_event_type_len: int,
    events: list[Event],
) -> None:
    """Print results."""
    col_1_width = max(max_entity_id_len, max_event_type_len + 6, len(COL1_HEADER))

    state_hdr = [f"{STATE_HEADER:{max_state_len}}"] if max_state_len else []
    attr_fields = [
        (
            attr,
            max(
                [len(str(state.attributes.get(attr, MISSING))) for state in states]
                + [len(attr)]
            )
        )
        for attr in attributes
    ]
    attr_hdrs = [f"{attr:{attr_len}}" for attr, attr_len in attr_fields]
    if other_attrs := any(entity_attrs.values()):
        attr_hdrs.append("attributes")
    print(
        f"{COL1_HEADER:{col_1_width}}",
        f"{'last_updated / time_fired':26}",
        *state_hdr,
        *attr_hdrs,
        sep=" | ",
    )

    state_hdr = ["-" * max_state_len] if max_state_len else []
    attr_hdrs = ["-" * attr_len for _, attr_len in attr_fields]
    hdr = "-|-".join(["-" * col_1_width, "-" * 26] + state_hdr + attr_hdrs)
    if other_attrs:
        hdr += "-|-"
        hdr += "-" * (get_terminal_size().columns - len(hdr))
    print(hdr)

    state_color: dict[str, str] = {}
    idx = 0
    for entity_id in entity_attrs:
        if entity_id not in state_color:
            state_color[entity_id] = COLORS_STATES[idx % len(COLORS_STATES)]
            idx += 1

    rows = sorted(states + events, key=lambda x: x.ts)
    prev_entity_id = None
    ts_idx = 0
    ts_color = COLORS_TS[0]
    sep = colored(" | ", ts_color)
    with suppress(IndexError):
        prev_date = rows[0].ts.date()

    for row in rows:
        if (row_date := row.ts.date()) != prev_date:
            ts_idx += 1
            ts_color = COLORS_TS[ts_idx % len(COLORS_TS)]
            sep = colored(" | ", ts_color)
            prev_date = row_date
        ts_str = colored(row.ts, ts_color)
        if isinstance(row, Event):
            event = row
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
            print(
                colored(f"{event_str:{fill}^{col_1_width}}", *colors),
                ts_str,
                ", ".join([f"{k}: {v}" for k, v in event.data.items()]),
                sep=sep,
            )
            prev_entity_id = None
        else:
            state = row
            if (entity_id := state.entity_id) != prev_entity_id:
                entity_id_str = prev_entity_id = entity_id
            else:
                entity_id_str = ""
            color = state_color[entity_id]
            _attrs = [
                colored(f"{state.attributes.get(attr, MISSING):<{attr_len}}", color)
                for attr, attr_len in attr_fields
            ]
            if other_attrs:
                attr_strs_pats = entity_attrs[entity_id]
                if any(isinstance(attr_str_pat, re.Pattern) for attr_str_pat in attr_strs_pats):
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
            print(
                colored(f"{entity_id_str:{col_1_width}}", color),
                ts_str,
                colored(f"{state.state:{max_state_len}}", color),
                *_attrs,
                sep=sep
            )


def main(args: ArgsNamespace, params: Params) -> str | int | None:
    """Print requested events and/or states."""
    global con

    con = sqlite3.connect(Path(args.dbpath).expanduser().resolve())

    try:
        if err := process_args(args, params):
            return err

        print_banner(args)

        all_entity_ids = get_all("states", "entity_id", "last_updated_ts", args)
        all_event_types = get_all("events", "event_type", "time_fired_ts", args)

        entity_attrs, max_entity_id_len = get_entity_ids_and_attributes(args, all_entity_ids)
        if not set(entity_attrs).issubset(all_entity_ids):
            print_error(
                "entity IDs not found in time window: "
                f"{', '.join(set(entity_attrs) - all_entity_ids)}"
            )
            return 1
        if entity_attrs:
            states = get_states(
                list(entity_attrs),
                include_attrs=any(entity_attrs.values()) or bool(args.attributes),
                start=args.start,
                end=args.end,
            )
            max_state_len = max(
                [len(state.state) for state in states] + [len(STATE_HEADER)]
            )
        else:
            states = []
            max_state_len = 0

        event_types, max_event_type_len = get_event_types(args, all_event_types)
        if not set(event_types).issubset(all_event_types):
            print_error(
                "event types not found in time window: "
                f"{', '.join(set(event_types) - all_event_types)}"
            )
            return 1
        if event_types:
            events = get_events(event_types, start=args.start, end=args.end)
        else:
            events = []

    finally:
        con.close()

    print_results(
        entity_attrs,
        args.attributes,
        max_entity_id_len,
        states,
        max_state_len,
        max_event_type_len,
        events,
    )


class ArgError(Exception):
    """Argument error."""


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
        nargs="+",
        default=[],
        help="global attributes",
        metavar="ATTR",
        dest="attributes",
    )
    state_group.add_argument(
        "-s",
        action="append",
        nargs="+",
        default=[],
        help="entity ID & optional attributes; use \"*\" for all attributes",
        metavar="VALUE",
        dest="entity_ids_attrs"
    )
    state_group.add_argument(
        "-sr",
        action="append",
        nargs="+",
        default=[],
        help="entity ID & optional attributes regular expressions",
        metavar="RE",
        dest="entity_ids_attrs_re"
    )

    # events

    event_group = parser.add_argument_group("events", "Event types")
    event_group.add_argument(
        "-e", nargs="+", default=[], help="event types", metavar="TYPE", dest="event_types"
    )
    event_group.add_argument(
        "-er",
        nargs="+",
        default=[],
        help="event type regular expressions",
        metavar="RE",
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
        "-SD",
        type=int,
        help="start DAYS ago",
        metavar="DAYS",
        dest="start_days_ago"
    )
    start_group.add_argument(
        "-SS",
        type=int,
        help="start STOPS ago",
        metavar="STOPS",
        dest="start_stops_ago"
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
        "-ED",
        type=int,
        help="end DAYS ago",
        metavar="DAYS",
        dest="end_days_ago"
    )
    end_group.add_argument(
        "-ES",
        type=int,
        help="end STOPS ago",
        metavar="STOPS",
        dest="end_stops_ago"
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
        for entity_id_attrs in args.entity_ids_attrs:
            if (entity_id := entity_id_attrs[0]).count(".") != 1:
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
        print_error(exc)
        sys.exit(2)

    return args, Params(start_specified, end_specified, window_specified)


if __name__ == "__main__":
    args, params = parse_args()
    sys.exit(main(args, params))
