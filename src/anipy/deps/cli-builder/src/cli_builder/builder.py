import inspect
import sys
import shlex
import asyncio
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


class CLIApp:
    def __init__(self) -> None:
        self.commands: dict[str, tuple[_CommandHandler, range, dict[str, _ValidateFunc]]] = {}
        self.prompt = "> "

        if os.name == "posix":
            if sys.platform == "darwin":
                readline.parse_and_bind("bind -v")
                readline.parse_and_bind("bind ^I rl_complete")

            else:
                readline.parse_and_bind("tab: complete")

            readline.set_completer_delims(" \t\n;")
            readline.set_completer(self._complete)

    def raise_err(self, err_type: ErrorTypes, err_message: str | None = None) -> None:
        if err_message:
            print(f"{err_type.name.lower()}: {err_message}")
        else:
            print(f"{err_type.name.lower()}")

    def completer(self, text, state):
        return None

    def _complete(self, text, state):
        tokens = readline.get_line_buffer().split()

        if len(tokens) < 2:
            options = [c for c in self.commands if c.startswith(text)]

            if state < len(options):
                return options[state]

        else:
            return self.completer(text, state)

    def _show_help(self, c: str | None = None) -> None:
        shown_commands = []

        for command, (callback, _, _) in self.commands.items():
            if c == command or c is None:
                if callback not in shown_commands:
                    shown_commands.append(callback)
                    args_line = []

                    for arg, annotation in inspect.get_annotations(callback).items():
                        if arg != "return":
                            if isinstance(annotation, UnionType):
                                args = get_args(annotation)
                                type = args[0].__name__
                                args_line.append(f"[{arg} {type}]")
                            else:
                                args_line.append(f"<{arg} {annotation.__name__}>")

                    aliases = getattr(callback, "__aliases__", [])

                    if aliases and args_line:
                        line = f" {', '.join(aliases)} -> {command}\n    {' '.join(args_line)} - {callback.__doc__}"

                    elif aliases:
                        line = f" {', '.join(aliases)} -> {command}\n    {callback.__doc__}"

                    elif args_line:
                        line = f" {command}\n    {' '.join(args_line)} - {callback.__doc__}"

                    else:
                        line = f" {command}\n    {callback.__doc__}"

                    print(line + "\n")

    def on(self, aliases: list[str] = [], validate: dict[str, Callable] = {}):
        def wrapper(func) -> None:
            command = func.__name__.replace("_", "-")

            argc_max = func.__code__.co_argcount + 1
            argc_min = 0

            sig = inspect.signature(func)
            for _, param in sig.parameters.items():
                if param.default is not None:
                    argc_min += 1

            self.commands[command] = (func, range(argc_min, argc_max), validate)

            setattr(func, "__aliases__", aliases)
            for a in aliases:
                self.commands[a] = self.commands[command]

            return func

        return wrapper

    async def run(self) -> None:
        while True:
            full = input(self.prompt)

            for usr_input in full.split(";"):
                usr_input = usr_input.strip()

                if usr_input:
                    try:
                        tokens = shlex.split(usr_input)
                    except Exception:
                        usr_input += '"'
                        tokens = shlex.split(usr_input)

                    command = tokens[0]
                    args = tokens[1:]

                    if command in self.commands:
                        callback, argc_range, validate = self.commands[command]
                        callback_annotations = inspect.get_annotations(callback)

                        if len(args) not in argc_range:
                            self._show_help(command)
                            if argc_range.start - argc_range.stop > 1:
                                self.raise_err(ErrorTypes.INSUFFICIENT_ARGS, f"expected from {argc_range.start} to {argc_range.stop} arguments, got {len(args)}")
                            else:
                                self.raise_err(ErrorTypes.INSUFFICIENT_ARGS, f"expected {argc_range.start} argument{'s' if argc_range.start > 1 else ''}, got {len(args)}")
                            continue

                        skip = False
                        for i, arg in enumerate(args):
                            annotation = list(callback_annotations.items())[i]
                            annotation_arg = annotation[0]
                            annotation_args = get_args(annotation[1])

                            if annotation_args:
                                annotation_type = next((i.__name__ for i in annotation_args if i is not type(None)))
                            else:
                                annotation_type = annotation[1].__name__

                            validate_func = validate.get(annotation_arg, None)

                            match annotation_type:
                                case "str":
                                    pass

                                case "int":
                                    try:
                                        arg = int(arg)
                                    except ValueError:
                                        self._show_help(command)
                                        self.raise_err(ErrorTypes.INVALID_ARGS, f"expected type 'int' for argument '{annotation_arg}'")
                                        skip = True
                                        break

                                case "list":
                                    arg = arg.split(",")

                                case _:
                                    self._show_help(command)
                                    self.raise_err(ErrorTypes.INVALID_ARGS, f"invalid type '{annotation_type.__name__}' for argument '{annotation_arg}'")
                                    skip = True
                                    break

                            if validate_func and not validate_func(arg):
                                self._show_help(command)
                                self.raise_err(ErrorTypes.ARG_VALIDATION_FAILED, annotation_arg)
                                skip = True
                                break

                            args[i] = arg

                        if skip:
                            continue

                        if asyncio.iscoroutinefunction(callback):
                            await callback(*args)

                        else:
                            callback(*args)

                    elif command in ("q", "quit"):
                        return

                    elif command in ("h", "help"):
                        self._show_help()

                    else:
                        self.raise_err(ErrorTypes.CMD_NOTFOUND, "try help")
