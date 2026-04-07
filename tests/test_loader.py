import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'scripts')))

import json
import tempfile
import unittest
from loader import load, validate, parse_int


FIXTURES = os.path.join(os.path.dirname(__file__), 'fixtures')


class TestParseInt(unittest.TestCase):

    def test_hex_string(self):
        self.assertEqual(parse_int('0x08000000'), 0x08000000)

    def test_decimal_string(self):
        self.assertEqual(parse_int('1024'), 1024)

    def test_integer_passthrough(self):
        self.assertEqual(parse_int(4096), 4096)

    def test_zero_hex(self):
        self.assertEqual(parse_int('0x0'), 0)


class TestLoadFixture(unittest.TestCase):

    def test_load_returns_sections_and_diagram(self):
        sections, diagram = load(os.path.join(FIXTURES, 'sample_diagram.json'))
        self.assertIsInstance(sections, list)
        self.assertIsInstance(diagram, dict)
        self.assertGreater(len(sections), 0)

    def test_hex_addresses_normalized(self):
        sections, _ = load(os.path.join(FIXTURES, 'sample_diagram.json'))
        flash = next(s for s in sections if s.id == 'Flash')
        self.assertEqual(flash.address, 0x08000000)
        self.assertEqual(flash.size, 0x20000)

    def test_optional_name(self):
        sections, _ = load(os.path.join(FIXTURES, 'sample_diagram.json'))
        text = next(s for s in sections if s.id == 'text')
        self.assertEqual(text.name, 'Code')

    def test_section_without_name_is_none(self):
        sections, _ = load(os.path.join(FIXTURES, 'sample_diagram.json'))
        rodata = next(s for s in sections if s.id == 'rodata')
        self.assertIsNone(rodata.name)

    def test_default_type_is_section(self):
        sections, _ = load(os.path.join(FIXTURES, 'sample_diagram.json'))
        rodata = next(s for s in sections if s.id == 'rodata')
        self.assertEqual(rodata.type, 'section')

    def test_area_type(self):
        sections, _ = load(os.path.join(FIXTURES, 'sample_diagram.json'))
        flash = next(s for s in sections if s.id == 'Flash')
        self.assertEqual(flash.type, 'area')

    def test_flags_parsed(self):
        sections, _ = load(os.path.join(FIXTURES, 'sample_diagram.json'))
        text = next(s for s in sections if s.id == 'text')
        self.assertIn('grows-up', text.flags)

    def test_empty_flags_default(self):
        sections, _ = load(os.path.join(FIXTURES, 'sample_diagram.json'))
        rodata = next(s for s in sections if s.id == 'rodata')
        self.assertEqual(rodata.flags, [])


class TestLoadErrors(unittest.TestCase):

    def _write_tmp(self, data):
        f = tempfile.NamedTemporaryFile(mode='w', suffix='.json',
                                        delete=False, encoding='utf-8')
        json.dump(data, f)
        f.close()
        return f.name

    def test_missing_id_raises(self):
        path = self._write_tmp({"sections": [{"address": "0x0", "size": "0x100"}]})
        with self.assertRaises(ValueError):
            load(path)

    def test_missing_address_raises(self):
        path = self._write_tmp({"sections": [{"id": "x", "size": "0x100"}]})
        with self.assertRaises(ValueError):
            load(path)

    def test_invalid_type_raises(self):
        path = self._write_tmp({"sections": [
            {"id": "x", "address": "0x0", "size": "0x100", "type": "invalid"}
        ]})
        with self.assertRaises(ValueError):
            load(path)


class TestValidate(unittest.TestCase):

    def test_valid_fixture_passes(self):
        errors = validate(os.path.join(FIXTURES, 'sample_diagram.json'))
        self.assertEqual(errors, [])

    def test_missing_sections_error(self):
        f = tempfile.NamedTemporaryFile(mode='w', suffix='.json',
                                        delete=False, encoding='utf-8')
        json.dump({"title": "no sections"}, f)
        f.close()
        errors = validate(f.name)
        self.assertTrue(any("sections" in e for e in errors))

    def test_bad_json_error(self):
        f = tempfile.NamedTemporaryFile(mode='w', suffix='.json',
                                        delete=False, encoding='utf-8')
        f.write("not json {")
        f.close()
        errors = validate(f.name)
        self.assertTrue(any("JSON" in e for e in errors))


if __name__ == '__main__':
    unittest.main()
