import inspect
import sys
import shlex
import os

import readline

from types import UnionType
from typing import Callable, Any, get_args
from enum import IntEnum


class ErrorTypes(IntEnum):
    CMD_NOTFOUND = 0x10

    INSUFFICIENT_ARGS = 0x20
    INVALID_ARGS = 0x21
    ARG_VALIDATION_FAILED = 0x22

    NETWORK_ERROR = 0x30
    REQUEST_ERROR = 0x31

    INVALID_RESULT = 0x40
    INVALID_CONTEXT = 0x41

    FILE_EXISTS = 0x50
    FILE_NOT_EXISTS = 0x51
    DIR_EXISTS = 0x52
    DIR_NOT_EXISTS = 0x53


type _ValidateFunc = Callable[[Any], bool]
type _CommandHandler = Callable[..., None]


class CommandRegistry:
    def __init__(self) -> None:
        self._commands: dict[str, tuple[_CommandHandler, range, dict[str, _ValidateFunc]]] = {}

    def register(self, func: _CommandHandler, aliases: list[str], validate: dict[str, _ValidateFunc]) -> str:
        command = func.__name__.replace("_", "-")
        argc_max = func.__code__.co_argcount + 1
        argc_min = 0
        for _, param in inspect.signature(func).parameters.items():
            if param.default is not None:
                argc_min += 1
        self._commands[command] = (func, range(argc_min, argc_max), validate)
        setattr(func, "__aliases__", aliases)
        for alias in aliases:
            self._commands[alias] = self._commands[command]
        return command

    def lookup(self, name: str) -> tuple[_CommandHandler, range, dict[str, _ValidateFunc]] | None:
        return self._commands.get(name)

    def names(self) -> list[str]:
        return list(self._commands.keys())

    def items(self):
        return self._commands.items()


_COERCERS: dict[str, Callable[[str], Any]] = {
    "str": lambda x: x,
    "int": int,
    "list": lambda x: x.split(","),
}


def coerce_arg(raw: str, type_name: str) -> Any:
    if type_name not in _COERCERS:
        raise TypeError(type_name)

    try:
        return _COERCERS[type_name](raw)

    except (ValueError, TypeError):
        raise ValueError(type_name)


class HelpFormatter:
    def format(self, command: str, callback: _CommandHandler) -> str:
        args_line = []
        for arg, annotation in inspect.get_annotations(callback).items():
            if arg != "return":
                if isinstance(annotation, UnionType):
                    inner = get_args(annotation)
                    type_name = next(a.__name__ for a in inner if a is not type(None))
                    args_line.append(f"[{arg} {type_name}]")
                else:
                    args_line.append(f"<{arg} {annotation.__name__}>")

        aliases = getattr(callback, "__aliases__", [])
        alias_prefix = f" {', '.join(aliases)} -> {command}\n" if aliases else f" {command}\n"
        body = f"    {' '.join(args_line)} - {callback.__doc__}" if args_line else f"    {callback.__doc__}"
        return alias_prefix + body

    def print_one(self, name: str, registry: CommandRegistry) -> None:
        seen = []
        for command, (callback, _, _) in registry.items():
            if command == name and callback not in seen:
                seen.append(callback)
                print(self.format(command, callback) + "\n")

    def print_all(self, registry: CommandRegistry) -> None:
        seen = []
        for command, (callback, _, _) in registry.items():
            if callback not in seen:
                seen.append(callback)
                print(self.format(command, callback) + "\n")


class CLIApp:
    def __init__(self) -> None:
        self._registry = CommandRegistry()
        self._formatter = HelpFormatter()
        self.prompt = "> "

        if os.name == "posix":
            if sys.platform == "darwin":
                readline.parse_and_bind("bind -v")
                readline.parse_and_bind("bind ^I rl_complete")
            else:
                readline.parse_and_bind("tab: complete")
            readline.set_completer_delims(" \t\n;")
            readline.set_completer(self._complete)

    def raise_err(self, err_type: ErrorTypes, *args) -> None:
        if args:
            print(f"\033[31mERROR: {err_type.name}:", *args, "\033[0m")
        else:
            print(f"\033[31mERROR: {err_type.name}\033[0m")

    def completer(self, text, state):
        return None

    def _complete(self, text, state):
        tokens = readline.get_line_buffer().split()
        if len(tokens) < 2:
            options = [c for c in self._registry.names() if c.startswith(text)]
            if state < len(options):
                return options[state]
        else:
            return self.completer(text, state)

    def _show_help(self, c: str | None = None) -> None:
        if c is None:
            self._formatter.print_all(self._registry)
        else:
            self._formatter.print_one(c, self._registry)

    def on(self, aliases: list[str] = [], validate: dict[str, Callable] = {}):
        def wrapper(func):
            self._registry.register(func, aliases, validate)
            return func
        return wrapper

    async def run(self) -> None:
        while True:
            full = input(self.prompt)

            for usr_input in full.split(";"):
                usr_input = usr_input.strip()
                if not usr_input:
                    continue

                try:
                    tokens = shlex.split(usr_input)
                except Exception:
                    tokens = shlex.split(usr_input + '"')

                command, *args = tokens

                if command in ("q", "quit"):
                    return

                if command in ("h", "help"):
                    self._show_help()
                    continue

                entry = self._registry.lookup(command)
                if entry is None:
                    self.raise_err(ErrorTypes.CMD_NOTFOUND, "try help")
                    continue

                callback, argc_range, validate = entry
                annotations = inspect.get_annotations(callback)

                if len(args) not in argc_range:
                    self._show_help(command)
                    span = argc_range.stop - argc_range.start
                    if span > 1:
                        self.raise_err(ErrorTypes.INSUFFICIENT_ARGS, f"expected from {argc_range.start} to {argc_range.stop} arguments, got {len(args)}")
                    else:
                        self.raise_err(ErrorTypes.INSUFFICIENT_ARGS, f"expected {argc_range.start} argument{'s' if argc_range.start > 1 else ''}, got {len(args)}")
                    continue

                skip = False
                for i, (ann_name, ann_type) in enumerate(list(annotations.items())[:len(args)]):
                    inner = get_args(ann_type)
                    type_name = next((a.__name__ for a in inner if a is not type(None)), None) if inner else ann_type.__name__

                    try:
                        args[i] = coerce_arg(args[i], type_name)

                    except TypeError:
                        self._show_help(command)
                        self.raise_err(ErrorTypes.INVALID_ARGS, f"invalid type '{type_name}' for argument '{ann_name}'")
                        skip = True
                        break
                    except ValueError:
                        self._show_help(command)
                        self.raise_err(ErrorTypes.INVALID_ARGS, f"expected type '{type_name}' for argument '{ann_name}'")
                        skip = True
                        break

                    validate_func = validate.get(ann_name)
                    if validate_func and not validate_func(args[i]):
                        self._show_help(command)
                        self.raise_err(ErrorTypes.ARG_VALIDATION_FAILED, ann_name)
                        skip = True
                        break

                if skip:
                    continue

                if inspect.iscoroutinefunction(callback):
                    await callback(*args)
                else:
                    callback(*args)
