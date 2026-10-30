# -*- coding: utf-8 -*-
"""
Utility/common code of library.
"""

__author__ = "Grzegorz Latuszek, Michal Ernst, Marcin Usielski"
__copyright__ = "Copyright (C) 2018-2026, Nokia"
__email__ = (
    "grzegorz.latuszek@nokia.com, michal.ernst@nokia.com, marcin.usielski@nokia.com"
)

import collections.abc
import copy
import importlib
import logging
import re
from functools import wraps
from math import isclose
from types import FunctionType, MethodType

from six import string_types, integer_types
from typing import List, Optional, Tuple
from moler.exceptions import MolerException


class ClassProperty(property):
    def __get__(self, cls, owner):
        return classmethod(self.fget).__get__(None, owner)()


def copy_list(src, deep_copy=False):
    """
    Copies list, if None then returns empty list
    :param src: List to copy
    :param deep_copy: if False then shallow copy, if True then deep copy
    :return: Copied list
    """
    if src is None:
        return []
    if deep_copy:
        return copy.deepcopy(src)
    return list(src)


def copy_dict(src, deep_copy=False):
    """
    Copies dict, if None then returns empty dict
    :param src: List to copy
    :param deep_copy: if False then shallow copy, if True then deep copy
    :return: Copied dict
    """
    if src is None:
        return {}
    if deep_copy:
        return copy.deepcopy(src)
    return dict(src)


def instance_id(instance):
    """
    Return id of instance in hex form.
    Helps in logs/debugs/development troubleshooting.
    """
    instance_id = hex(id(instance))[2:]  # remove leading 0x
    return instance_id


def camel_case_to_lower_case_underscore(string):
    """
    Split string by upper case letters.
    F.e. useful to convert camel case strings to underscore separated ones.
    @return words (list)
    """
    words = []
    from_char_position = 0
    for current_char_position, char in enumerate(string):
        if char.isupper() and from_char_position < current_char_position:
            words.append(string[from_char_position:current_char_position].lower())
            from_char_position = current_char_position
    words.append(string[from_char_position:].lower())
    return "_".join(words)


_re_escape_codes = re.compile(
    r"\x1B\[[0-?]*[ -/]*[@-~]"
)  # Regex to remove color codes from command output
_re_escape_codes_cursor = re.compile(r"\x1B(([\dA-F]+)|(\[\d+;\d+r)|(J))")


def remove_escape_codes(line):
    """
    :param line: line from terminal
    :return: line without terminal escape codes
    """
    line = re.sub(_re_escape_codes, "", line)
    line = re.sub(_re_escape_codes_cursor, "", line)
    return line


# ESC [ ? 12 h   Start the cursor blinking
# ESC [ ? 12 l   Stop blinking the cursor
# ESC [ ? 25 h   Show the cursor
# ESC [ ? 25 l   Show the cursor
# ESC [ ? 2004 l Control sequence odd character
# ESC [ ? 2004 h Control sequence odd character
_re_cursor_visibility_codes = re.compile(r"\x1B\[\?(12|25|2004)[hl]")


def remove_cursor_visibility_codes(multiline):
    """
    :param multiline: string from terminal holding single or multiple lines
    :return: line(s) without terminal escape codes related to cursor visibility
    """
    multiline = _re_cursor_visibility_codes.sub("", multiline)
    return multiline


# ESC [ <n> m    Text formatting as specified by <n>; <n> may mean bold/underline/some-color
# ESC [ m        Switch off text formatting (back to defaults)
_re_text_formatting_codes = re.compile(r"\x1B\[\d*m")


def remove_text_formatting_codes(multiline):
    """
    :param multiline: string from terminal holding single or multiple lines
    :return: line(s) without terminal escape codes related to text formatting
    """
    multiline = _re_text_formatting_codes.sub("", multiline)
    return multiline


# ESC ] 0 ; <string> BEL    Sets the console window’s (and icon) title to <string>.
# ESC ] 2 ; <string> BEL    Sets the console window’s title to <string>.
_re_console_title_codes = re.compile(r"\x1B\][02];[^\x07]+\x07")


def remove_window_title_codes(multiline):
    """
    :param multiline: string from terminal holding single or multiple lines
    :return: line(s) without terminal escape codes setting console window/icon title
    """
    multiline = _re_console_title_codes.sub("", multiline)
    return multiline


# ESC ] <string> BEL       Operating System Command (OSC) terminated by BEL.
# ESC ] <string> ESC \     Operating System Command (OSC) terminated by ST, e.g. systemd shell context:
#                          ESC ] 3008 ; start=<uuid>;user=<user>;...;type=shell ESC \
_re_osc_codes = re.compile(r"\x1B\][^\x07\x1B\r\n]*(?:\x07|\x1B\\)")


def remove_osc_codes(multiline):
    """
    :param multiline: string from terminal holding single or multiple lines
    :return: line(s) without terminal OSC (Operating System Command) escape codes
    """
    multiline = _re_osc_codes.sub("", multiline)
    return multiline


# ESC [ <n> C    Cursor forward (Right) by <n>
# ESC [ <n> X    Erase <n> characters from the current cursor position by overwriting them with a space character.
_re_space_fill_to_right_margin = re.compile(r"(\x1B\[\d+[XC])+(\r|\n)")


def remove_fill_spaces_right_codes(multiline):
    """
    :param multiline: string from terminal holding single or multiple lines
    :return: line(s) without spaces added till right VT-screen margin
    """
    multiline = _re_space_fill_to_right_margin.sub(r"\2", multiline)
    return multiline


# ESC [ H        Move Cursor Home to let it write from first column
_re_overwritten_left_writes = re.compile(
    r"^[^\n\r]*\x1B\[H(.)", flags=re.DOTALL | re.MULTILINE
)


def remove_overwritten_left_write(multiline):
    """
    :param multiline: string from terminal holding single or multiple lines
    :return: line without spaces added till right VT-screen margin
    """
    multiline = _re_overwritten_left_writes.sub(r"\1", multiline)
    return multiline


_re_remove_terminal_last_cmd_status = re.compile(r"\x1b]777;notify;.*\x07")


def remove_terminal_last_cmd_status(line):
    """
    :param line: line from terminal
    :return: line without terminal last cmd status
    """
    line = re.sub(_re_remove_terminal_last_cmd_status, "", line)
    return line


def remove_all_known_special_chars(line):
    """
    :param line: line from terminal
    :return: line without all known special chars
    """
    line = remove_overwritten_left_write(line)
    line = remove_osc_codes(line)
    line = remove_escape_codes(line)
    line = remove_cursor_visibility_codes(line)
    line = remove_fill_spaces_right_codes(line)
    line = remove_text_formatting_codes(line)
    return line


def create_object_from_name(full_class_name, constructor_params):
    name_splitted = full_class_name.split(".")
    module_name = ".".join(name_splitted[:-1])
    class_name = name_splitted[-1]

    imported_module = importlib.import_module(module_name)
    class_imported = getattr(imported_module, class_name)
    obj = class_imported(**constructor_params)
    return obj


def update_dict(target_dict, expand_dict):
    # pylint: disable-next=unused-variable
    for key, value in expand_dict.items():
        if (key in target_dict and isinstance(target_dict[key], dict) and isinstance(expand_dict[key],
                                                                                     collections.abc.Mapping)):
            update_dict(target_dict[key], expand_dict[key])
        else:
            target_dict[key] = expand_dict[key]


def compare_objects(
    first_object, second_object, significant_digits=None, exclude_types=None
):
    """
    Return difference between two objects.
    :param first_object: first object to compare
    :param second_object: second object to compare
    :param significant_digits: use to properly compare numbers(float arithmetic error)
    :param exclude_types: types which be excluded from comparison
    :return: difference between two objects
    """
    if exclude_types is None:
        exclude_types = set()

    diff = diff_data(
        first_object=first_object,
        second_object=second_object,
        significant_digits=significant_digits,
        exclude_types=exclude_types,
    )

    return diff


def diff_data(
    first_object, second_object, significant_digits=None, exclude_types=None, msg=None
) -> str:
    """
    Compare two objects recursively and return a message indicating any differences.

    :param first_object: The first object for comparison.
    :param second_object: The second object for comparison.
    :param significant_digits: The number of significant digits to consider for float
                               comparison.
    :param exclude_types: A list of types to exclude from comparison.
    :param msg: A message to prepend to any difference messages.
                Defaults to 'root' if not provided.

    :return: A message indicating the differences, or an empty string if objects are
             equal.
    """
    if msg is None:
        msg = "root"
    type_first = type(first_object)
    type_second = type(second_object)
    if type_first != type_second:
        return f"{msg} {first_object} is type of {type_first} but {second_object} is type of {type_second}"
    elif exclude_types is not None and type_first in exclude_types:
        return ""
    elif isinstance(first_object, (list, tuple)):
        return _compare_lists(
            first_object=first_object,
            second_object=second_object,
            significant_digits=significant_digits,
            exclude_types=exclude_types,
            msg=msg,
        )
    elif isinstance(first_object, dict):
        return _compare_dicts(
            first_object=first_object,
            second_object=second_object,
            significant_digits=significant_digits,
            exclude_types=exclude_types,
            msg=msg,
        )
    elif isinstance(first_object, set):
        return _compare_sets(
            first_object=first_object, second_object=second_object, msg=msg
        )
    elif isinstance(first_object, float):
        return _compare_floats(
            first_object=first_object,
            second_object=second_object,
            msg=msg,
            significant_digits=significant_digits
        )
    else:
        if first_object != second_object:
            return f"{msg} First value '{first_object}' is different from the second '{second_object}."

    return ""


def _compare_floats(first_object: float, second_object: float, msg: str,
                    significant_digits: Optional[int] = None) -> str:
    """
    Compare two floats and return a message indicating any differences.
    :param first_object: The first float for comparison.
    :param second_object: The second float for comparison.
    :param msg: A message to prepend to any difference messages.
    :param significant_digits: The number of significant digits to consider for float
                               comparison.
    :return: A message indicating the differences, or an empty string if objects are equal.
    """
    abs_tol = 0.0001
    if significant_digits:
        abs_tol = 1.0 / 10**significant_digits
    if not isclose(first_object, second_object, abs_tol=abs_tol):
        return f"{msg} the first value '{first_object}' is different from the second value '{second_object}'."
    return ""


def _compare_dicts(
    first_object, second_object, msg, significant_digits=None, exclude_types=None
):
    """
    Compare two dictionaries recursively and return a message indicating any
     differences.

    :param first_object: The first dictionary for comparison.
    :param second_object: The second dictionary for comparison.
    :param significant_digits: The number of significant digits to consider for float
                               comparison.
    :param exclude_types: A list of types to exclude from comparison.
    :param msg: A message to prepend to any difference messages.

    :return: A message indicating the differences, or an empty string if objects are
             equal.
    """
    keys_first = set(first_object.keys())
    keys_second = set(second_object.keys())
    diff = keys_first ^ keys_second
    if diff:
        for key in keys_first:
            if key not in keys_second:
                return f"{msg} key '{key}' is in the first {first_object} but not in the second dict {second_object}."
        for key in keys_second:
            if key not in keys_first:
                return f"{msg} key '{key}' is in the second {second_object} but not in the first dict {first_object}."
    else:
        for key in keys_first:
            res = diff_data(
                first_object=first_object[key],
                second_object=second_object[key],
                significant_digits=significant_digits,
                exclude_types=exclude_types,
                msg=f"{msg} -> [{key}]",
            )
            if res:
                return res
    return ""


def _compare_sets(first_object, second_object, msg):
    """

    Compare two sets.

    :param first_object: The first object for comparison.
    :param second_object: The second object for comparison.
    :param msg: A message to prepend to any difference messages.
    :return: A message indicating the differences, or an empty string if objects are
     equal.
    """
    diff = first_object.symmetric_difference(second_object)
    if diff:
        for item in first_object:
            if item not in second_object:
                return (f"{msg} item '{item}' is in the first set '{first_object}'"
                        f" but not in the second set '{second_object}'.")
        for item in second_object:
            if item not in first_object:
                return (f"{msg} item '{item}' is in the second set '{second_object}'"
                        f" but not in the first set '{first_object}'.")
    return ""


def _compare_lists(
    first_object, second_object, msg, significant_digits=None, exclude_types=None
):
    """
    Compare two lists or tuples recursively and return a message indicating any
     differences.

    :param first_object: The first list or tuple for comparison.
    :param second_object: The second list or tuple for comparison.
    :param significant_digits: The number of significant digits to consider for float
                               comparison.
    :param exclude_types: A list of types to exclude from comparison.
    :param msg: A message to prepend to any difference messages.

    :return: A message indicating the differences, or an empty string if objects are
             equal.
    """
    len_first = len(first_object)
    len_second = len(second_object)
    if len_first != len_second:
        return f"{msg} List '{first_object}' has {len_first} item(s) but '{second_object}' has {len_second} item(s)"
    max_element = len(first_object)
    for i in range(0, max_element):
        res = diff_data(
            first_object=first_object[i],
            second_object=second_object[i],
            msg=f"{msg} -> [{i}]",
            significant_digits=significant_digits,
            exclude_types=exclude_types,
        )
        if res:
            return res
    return ""


def convert_to_number(value, none_if_cannot_convert: bool = False):
    """
    Convert value to Python number type.
    :param value: value to convert
    :param none_if_cannot_convert: If True and obj is not int then return None
    :return: converted value if possible, otherwise original
    """
    if value and is_digit(value):
        try:
            value = int(value)
        except ValueError:
            try:
                value = float(value)
            except ValueError:
                if none_if_cannot_convert:
                    return None
    else:
        if none_if_cannot_convert:
            return None
    return value


def is_digit(value):
    """
    Check that value is digit.
    :param value: value to check
    :return: True if value is digit, otherwise False
    """
    try:
        float(value)
        return True
    except ValueError:
        return False


def convert_to_int(obj, none_if_cannot_convert: bool = False):
    """
    Convert element of object structure to int if it's possible.
    :param obj: object to convert
    :param none_if_cannot_convert: If True and obj is not int then return None
    """
    if isinstance(obj, (string_types, integer_types)):
        try:
            return int(obj)
        except ValueError:
            if none_if_cannot_convert:
                return None
            return obj
    elif isinstance(obj, dict):
        return {k: convert_to_int(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_to_int(v) for v in obj]
    else:
        if none_if_cannot_convert:
            return None
        return obj


class ForwardingHandler(logging.Handler):
    """
    Take log record and pass it to target_logger
    """

    def __init__(self, target_logger_name):
        super(ForwardingHandler, self).__init__(level=1)
        self.target_logger_name = target_logger_name
        self.target_logger = logging.getLogger("moler")

    def emit(self, record):
        """
        Emit a record.

        Output the record to the target_logger, catering for rollover as described
        in doRollover().
        """
        record.name = self.target_logger_name

        if (record.levelno == logging.INFO) or (record.levelname == "INFO"):
            record.levelno = logging.DEBUG
            record.levelname = "DEBUG"

        self.target_logger.handle(record)


def call_base_class_method_with_same_name(obj):
    """
    Run base class method.

    :param obj: class object which methods will be decorated.
    :return: class object with decorated methods
    """
    if hasattr(obj, "__dict__"):
        if obj.__dict__.items():
            for attributeName in dir(obj):
                attribute = getattr(obj, attributeName)

                if "_decorate" in dir(attribute):
                    if isinstance(attribute, (FunctionType, MethodType)):
                        setattr(obj, attributeName, _wrapper(method=attribute, obj=obj))

    return obj


def mark_to_call_base_class_method_with_same_name(func):
    """
    Mark method which base class method with same name will be call.
    :param func: function to mark.
    :return: marked function
    """
    func._decorate = True  # pylint: disable=protected-access
    return func


def _wrapper(method, obj):
    if hasattr(method, "_already_decorated") and method._already_decorated:  # pylint: disable=protected-access
        return method

    @wraps(method)
    def wrapped(*args, **kwargs):
        base_method = getattr(obj.__bases__[0], method.__name__)
        base_result = base_method(*args, **kwargs)

        result = method(*args, **kwargs)
        update_dict(base_result, result)

        return base_result

    wrapped._already_decorated = True  # pylint: disable=protected-access
    return wrapped


def non_printable_chars_to_hex(source):
    """
    Converts input string into hex for all non printable chars, printable chars remain unchanged.
    :param source: input string.
    :return: output string witch exchanged chars.
    """
    import string

    output = ""
    for char in source:
        if char not in string.printable or char in ["\n", "\r"]:
            output += f"\\x{ord(char):02x}"
        else:
            output += char
    return output


def all_chars_to_hex(source):
    """
    Converts input string into hex for all chars.
    :param source: input string.
    :return: output string witch exchanged chars.
    """
    output = ""
    for char in source:
        output += f"\\x{ord(char):02x}"
    return output


def regexp_without_anchors(regexp):
    """
    Remove anchors from beginning (^) and ending ($) of the regexp.
    :param regexp: compiled regexp
    :return: compiled regexp without anchors
    """
    regexp_str = regexp.pattern.strip()
    org_regexp_str = regexp_str
    if len(org_regexp_str) >= 2:
        if "^" == regexp_str[0]:
            regexp_str = regexp_str[1:]
        if "$" == regexp_str[-1] and "\\" != regexp_str[-2]:
            regexp_str = regexp_str[:-1]
    if regexp_str == org_regexp_str:
        return regexp
    return re.compile(regexp_str)


def _get_states_to_remove_from_sm(source_sm: dict, state_to_remove: str) -> List[str]:
    states_from_state_to_remove = []
    for from_state in source_sm.keys():
        for to_state in source_sm[from_state].keys():
            if to_state == state_to_remove:
                states_from_state_to_remove.append(from_state)
    return states_from_state_to_remove


def remove_state_from_sm(source_sm: dict, source_transitions: dict, state_to_remove: str,
                         forbidden: Optional[dict] = None) -> Tuple[dict, dict]:
    """
    Remove a state from a state machine dict.
    :param source_sm: a dict with a state machine description
    :param source_transitions: a dict with a state machine transitions
    :param state_to_remove: name of state to remove
    :return: tuple with 2 dicts without state_to_remove, 0 - new state machine, 1 - new transitions
    """
    new_sm = copy.deepcopy(source_sm)
    new_transitions = copy.deepcopy(source_transitions)

    states_from_state_to_remove = _get_states_to_remove_from_sm(source_sm=source_sm, state_to_remove=state_to_remove)

    for to_state in states_from_state_to_remove:
        if to_state == state_to_remove:
            continue
        for new_from in states_from_state_to_remove:
            if new_from == to_state:
                continue
            if forbidden and new_from in forbidden and forbidden[new_from] == to_state:
                continue
            if new_from not in new_sm:
                new_sm[new_from] = {}
            if new_from not in new_transitions:
                new_transitions[new_from] = {}

            new_sm[new_from][to_state] = copy.deepcopy(source_sm[state_to_remove][to_state])
            if 'execute_command' in source_sm[new_from][state_to_remove]:
                new_sm[new_from][to_state]['execute_command'] = source_sm[new_from][state_to_remove]['execute_command']

            if state_to_remove in source_transitions and to_state in source_transitions[state_to_remove]:
                new_transitions[new_from][to_state] = copy.deepcopy(source_transitions[state_to_remove][to_state])
            else:
                new_transitions[new_from][to_state] = {
                    "action": [
                        "_execute_command_to_change_state"
                    ],
                }

    _delete_state(sm=new_sm, state_to_remove=state_to_remove)
    _delete_state(sm=new_transitions, state_to_remove=state_to_remove)
    _delete_empty_states(new_sm)
    _delete_empty_states(new_transitions)

    return (new_sm, new_transitions)


def _delete_state(sm: dict, state_to_remove: str) -> None:
    """
    Delete state from a state machine dict (in place).
    :param sm: dict with state machine
    :param state_to_remove: name of state to delete
    :return: None
    """
    if state_to_remove in sm:
        del sm[state_to_remove]
    for from_state in sm:
        if from_state in sm and state_to_remove in sm[from_state]:
            del sm[from_state][state_to_remove]


def _delete_empty_states(sm: dict) -> None:
    """
    Delete empty states from a state machine dict (in place).
    :param sm: dict with state machine
    :return: None
    """
    states = list(sm.keys())
    for state in states:
        if sm[state] is None or not sm[state]:
            del sm[state]


def remove_state_hops_from_sm(source_hops: dict, state_to_remove: str, additional_hops: Optional[dict] = None,
                              forbidden_hops: Optional[dict] = None) -> dict:
    """
    Remove a state from a state machine dict.
    :param source_sm: a dict with state machine description
    :param state_to_remove: name of state to remove
    :param forbidden_hops: dict with forbidden transitions after remove, key is source, value is destination
    :return: a new state machine hops dict without state_to_remove
    """
    new_hops = copy.deepcopy(source_hops)

    for old_from_state in source_hops.keys():
        item = source_hops[old_from_state]
        for old_dest_state in item.keys():
            old_via_state = item[old_dest_state]
            if old_via_state == state_to_remove:
                if state_to_remove in source_hops and old_dest_state in source_hops[state_to_remove]:
                    if source_hops[state_to_remove][old_dest_state] == old_from_state:
                        msg = (f"Found cycle from '{old_from_state}' to '{old_dest_state}' via "
                               f"'{source_hops[state_to_remove][old_dest_state]}'. "
                               f"Please verify state hops: {source_hops}")
                        raise MolerException(msg)
                    new_via_state = source_hops[old_via_state][old_dest_state]
                    if (forbidden_hops and old_from_state in forbidden_hops and (
                            old_dest_state in forbidden_hops[old_from_state]) and (
                            new_via_state == forbidden_hops[old_from_state][old_dest_state])):
                        if old_from_state in new_hops and old_dest_state in new_hops[old_from_state]:
                            del new_hops[old_from_state][old_dest_state]
                    else:
                        new_hops[old_from_state][old_dest_state] = new_via_state
                else:
                    del new_hops[old_from_state][old_dest_state]

    _del_state_hops_after_hops_processing(source_hops, state_to_remove, new_hops, additional_hops)

    return new_hops


def _del_state_hops_after_hops_processing(source_hops: dict, state_to_remove: str, new_hops: dict,
                                          additional_hops: Optional[dict]) -> None:
    for old_from_state in source_hops.keys():
        if old_from_state in new_hops and state_to_remove in new_hops[old_from_state]:
            del new_hops[old_from_state][state_to_remove]

    if state_to_remove in new_hops:
        del new_hops[state_to_remove]

    _delete_empty_states(new_hops)
    if additional_hops:
        update_dict(new_hops, additional_hops)
