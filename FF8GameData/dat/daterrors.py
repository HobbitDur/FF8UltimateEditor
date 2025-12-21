from typing import List, Optional, Dict, Any
from datetime import datetime


class AICodeError(Exception):
    """Enhanced command error that collects multiple errors with timestamps and contexts"""

    _errors: List[Dict[str, Any]] = []
    _auto_print = True  # Control whether to auto-print

    def __init__(self, message: str = "", context: Optional[Dict[str, Any]] = None):
        self.message = message
        self.timestamp = datetime.now()
        self.context = context or {}

        if message:  # Only add non-empty messages
            error_entry = {
                'title': self.__class__.__name__,
                'message': message,
                'timestamp': self.timestamp,
                'context': self.context
            }
            AICodeError._errors.append(error_entry)
            if AICodeError._auto_print:
                print(f"{message}")
        super().__init__(message)

    def __str__(self):
        return self.message

    @classmethod
    def get_errors(cls) -> List[Dict[str, Any]]:
        """Get all collected errors with details"""
        return cls._errors.copy()

    @classmethod
    def get_error_messages(cls) -> List[str]:
        """Get only the error messages"""
        return ["<i>" + error['title'] + "</i> - " + error['message'] for error in cls._errors]

    @classmethod
    def clear_errors(cls):
        """Clear all collected errors"""
        cls._errors.clear()

    @classmethod
    def has_errors(cls) -> bool:
        """Check if any errors were collected"""
        return len(cls._errors) > 0

    @classmethod
    def get_error_count(cls) -> int:
        """Get the number of collected errors"""
        return len(cls._errors)

    @classmethod
    def format_errors_for_display(cls) -> str:
        """Format errors as plain text bullet list for QMessageBox detailed text"""
        if not cls._errors:
            return "No errors"

        bullet_items = "\n".join([f"• {error}<br/>" for error in AICodeError.get_error_messages()])
        return f"Found {cls.get_error_count()} error(s):<br/>{bullet_items}"

    @classmethod
    def set_auto_print(cls, enabled: bool):
        """Enable/disable automatic printing"""
        cls._auto_print = enabled


# To be deleted as it shouldn't be used
class OpCodeNotFound(AICodeError):
    def __init__(self, op_code: int):
        message = f"No op_code defined for op_id: {op_code}"
        super().__init__(message)


class FuncNameNotFound(AICodeError):
    def __init__(self, func_name: str):
        message = f"Didn't find func name: <b>{func_name}</b>"
        super().__init__(message)


class FuncNameUnexpected(AICodeError):
    def __init__(self, func_name_unexpected: str, func_name_expected: str):
        message = f"Unexpected func name: <b>{func_name_unexpected}</b>, expected {func_name_expected}"
        super().__init__(message)


class LineUnexpectedCharaError(AICodeError):
    def __init__(self, chara_unexpected: str, func_name_expected: str):
        message = f"Unexpected <b>{chara_unexpected}</b> in line {func_name_expected}"
        super().__init__(message)


class EmptyLineError(AICodeError):
    def __init__(self):
        message = f"Unexpected empty line"
        super().__init__(message)


class LineError(AICodeError):
    def __init__(self, message: str):
        super().__init__(message)


class BracketError(AICodeError):
    def __init__(self, message: str):
        super().__init__(message)


class SectionError(AICodeError):
    def __init__(self, message: str):
        super().__init__(message)


class ParamCountError(AICodeError):
    def __init__(self, message: str):
        super().__init__(message)


class ParamSlotIdEnableError(AICodeError):
    def __init__(self, slot_id_enable: str):
        super().__init__(f"Unexpected slot id enable: {slot_id_enable}")


class ParamAssignSlotIdError(AICodeError):
    def __init__(self, assign_slot_id: str):
        super().__init__(f"Unexpected assign slot id: {assign_slot_id}")


class ParamSlotIdError(AICodeError):
    def __init__(self, slot_id: str):
        super().__init__(f"Unexpected slot_id: {slot_id}")


class ParamLocalVarParamError(AICodeError):
    def __init__(self, local_var_param: str):
        super().__init__(f"Unexpected local var param: {local_var_param}")

class ParamLocalVarError(AICodeError):
    def __init__(self, local_var: str):
        super().__init__(f"Unexpected local_var : {local_var}")

class ParamBattleVarError(AICodeError):
    def __init__(self, battle_var: str):
        super().__init__(f"Unexpected battle_var : {battle_var}")

class ParamGlobalVarError(AICodeError):
    def __init__(self, global_var: str):
        super().__init__(f"Unexpected global_var : {global_var}")


class ParamSceneOutSlotIdError(AICodeError):
    def __init__(self, scene_out_slot_id: str):
        super().__init__(f"Unexpected scene out slot id: {scene_out_slot_id}")


class ParamMagicIdError(AICodeError):
    def __init__(self, magic_id: str):
        super().__init__(f"Unexpected magic id: {magic_id}")


class ParamMagicTypeError(AICodeError):
    def __init__(self, magic_type: str):
        super().__init__(f"Unexpected magic type: {magic_type}")


class ParamStatusAIError(AICodeError):
    def __init__(self, status_ai: str):
        super().__init__(f"Unexpected status ai: {status_ai}")


class ParamItemError(AICodeError):
    def __init__(self, item: str):
        super().__init__(f"Unexpected item: {item}")


class ComparatorError(AICodeError):
    def __init__(self, comparator: str):
        super().__init__(f"Unexpected comparator: {comparator}")


class SubjectIdError(AICodeError):
    def __init__(self, subject_id: str):
        super().__init__(f"Unexpected subject_id: {subject_id}")


class SubjectIdTenError(AICodeError):
    def __init__(self, subject_id_10: str):
        super().__init__(f"Unexpected subject_id_10: {subject_id_10}")


class ParamGfError(AICodeError):
    def __init__(self, gf: str):
        super().__init__(f"Unexpected gf: {gf}")


class ParamCardError(AICodeError):
    def __init__(self, card: str):
        super().__init__(f"Unexpected card: {card}")


class ParamSpecialActionError(AICodeError):
    def __init__(self, special_action: str):
        super().__init__(f"Unexpected special_action: {special_action}")
class ParamActivateError(AICodeError):
    def __init__(self, activate: str):
        super().__init__(f"Unexpected activate: {activate}")

class ParamTargetBasicError(AICodeError):
    def __init__(self, target_basic: str):
        super().__init__(f"Unexpected target_basic: {target_basic}")

class ParamTargetGenericError(AICodeError):
    def __init__(self, target_generic: str):
        super().__init__(f"Unexpected target_generic: {target_generic}")

class ParamBattleTextError(AICodeError):
    def __init__(self, battle_text: str):
        super().__init__(f"Unexpected battle_text: {battle_text}")


class ParamTargetSpecificError(AICodeError):
    def __init__(self, target_specific: str):
        super().__init__(f"Unexpected target_specific: {target_specific}")


class ParamTargetSlotError(AICodeError):
    def __init__(self, target_slot: str):
        super().__init__(f"Unexpected target_slot: {target_slot}")


class ParamAptitudeError(AICodeError):
    def __init__(self, aptitude: str):
        super().__init__(f"Unexpected aptitude: {aptitude}")


class ParamIntShiftError(AICodeError):
    def __init__(self, int_shift: str, shift: int):
        super().__init__(f"Unexpected IntShift: {int_shift} with shift: {shift}")
class ParamIntError(AICodeError):
    def __init__(self, int_value: str):
        super().__init__(f"Unexpected Int: {int_value}")
class ParamInt16Error(AICodeError):
    def __init__(self, int16_value: str):
        super().__init__(f"Unexpected Int16: {int16_value}")
class ParamPercentError(AICodeError):
    def __init__(self, percent: str):
        super().__init__(f"Unexpected percent: {percent}")
class ParamHpPercentError(AICodeError):
    def __init__(self, hp_percent: str):
        super().__init__(f"Unexpected hp_percent: {hp_percent}")
class ParamPercentElemError(AICodeError):
    def __init__(self, percent_elem: str):
        super().__init__(f"Unexpected percent_elem: {percent_elem}")
class ParamBoolError(AICodeError):
    def __init__(self, bool_value: str):
        super().__init__(f"Unexpected bool_value: {bool_value}")

class ParamMonsterAbilityError(AICodeError):
    def __init__(self, monster_ability: str):
        super().__init__(f"Unexpected monster_ability: {monster_ability}")


class ParamMonsterLineAbilityError(AICodeError):
    def __init__(self, monster_line_ability: str):
        super().__init__(f"Unexpected monster_line_ability: {monster_line_ability}")
