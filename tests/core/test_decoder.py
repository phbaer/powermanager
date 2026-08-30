from __future__ import annotations

import unittest

from powermanager_core.exceptions import RegisterDecodeError
from powermanager_core.modbus import (
    RegisterDataType,
    RegisterDefinition,
    RegisterTable,
    decode_registers,
)


def definition(data_type: RegisterDataType, **kwargs: object) -> RegisterDefinition:
    return RegisterDefinition("value", 30053, RegisterTable.INPUT, data_type, **kwargs)


class RegisterDecoderTest(unittest.TestCase):
    def test_decodes_signed_32_bit_value_with_scale(self) -> None:
        self.assertEqual(
            decode_registers([0xFFFF, 0xFE0C], definition(RegisterDataType.S32, scale=0.1)), -50.0
        )

    def test_invalid_sentinel_becomes_none_before_scaling(self) -> None:
        self.assertIsNone(
            decode_registers(
                [0xFFFF],
                definition(RegisterDataType.U16, invalid_values=frozenset({65535})),
            )
        )

    def test_documents_to_pdu_address_conversion(self) -> None:
        self.assertEqual(definition(RegisterDataType.U32).pdu_address, 30053)

    def test_rejects_short_reads(self) -> None:
        with self.assertRaises(RegisterDecodeError):
            decode_registers([1], definition(RegisterDataType.U32))

    def test_signed_invalid_sentinel_is_checked_before_sign_conversion(self) -> None:
        self.assertIsNone(
            decode_registers(
                [0x8000, 0x0000],
                definition(RegisterDataType.S32, invalid_values=frozenset({0x80000000})),
            )
        )
