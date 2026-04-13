import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'scripts')))

import json
import tempfile
import unittest
from loader import load, validate, parse_int, resolve_view_sections
from section import Section


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


class TestLoad(unittest.TestCase):

    def test_load_returns_dict(self):
        diagram = load(os.path.join(FIXTURES, 'sample_diagram.json'))
        self.assertIsInstance(diagram, dict)

    def test_load_has_views(self):
        diagram = load(os.path.join(FIXTURES, 'sample_diagram.json'))
        self.assertIn('views', diagram)
        self.assertGreater(len(diagram['views']), 0)

    def test_unknown_fields_are_ignored(self):
        f = tempfile.NamedTemporaryFile(mode='w', suffix='.json',
                                        delete=False, encoding='utf-8')
        json.dump({"views": [], "extra_field": "ignored"}, f)
        f.close()
        diagram = load(f.name)
        self.assertIsInstance(diagram, dict)


class TestValidate(unittest.TestCase):

    def test_valid_fixture_passes(self):
        errors = validate(os.path.join(FIXTURES, 'sample_diagram.json'))
        self.assertEqual(errors, [])

    def test_empty_diagram_is_valid(self):
        f = tempfile.NamedTemporaryFile(mode='w', suffix='.json',
                                        delete=False, encoding='utf-8')
        json.dump({"title": "no views"}, f)
        f.close()
        errors = validate(f.name)
        self.assertEqual(errors, [])

    def test_bad_json_error(self):
        f = tempfile.NamedTemporaryFile(mode='w', suffix='.json',
                                        delete=False, encoding='utf-8')
        f.write("not json {")
        f.close()
        errors = validate(f.name)
        self.assertTrue(any("JSON" in e for e in errors))

    def test_section_missing_name_is_error(self):
        f = tempfile.NamedTemporaryFile(mode='w', suffix='.json',
                                        delete=False, encoding='utf-8')
        json.dump({"views": [{"id": "v", "sections": [
            {"id": "x", "address": "0x0", "size": "0x100"}
        ]}]}, f)
        f.close()
        errors = validate(f.name)
        self.assertTrue(any("name" in e for e in errors))

    def test_section_missing_address_is_error(self):
        f = tempfile.NamedTemporaryFile(mode='w', suffix='.json',
                                        delete=False, encoding='utf-8')
        json.dump({"views": [{"id": "v", "sections": [
            {"id": "x", "size": "0x100", "name": "X"}
        ]}]}, f)
        f.close()
        errors = validate(f.name)
        self.assertTrue(any("address" in e for e in errors))

    def test_duplicate_section_id_within_view_is_error(self):
        f = tempfile.NamedTemporaryFile(mode='w', suffix='.json',
                                        delete=False, encoding='utf-8')
        json.dump({"views": [{"id": "v", "sections": [
            {"id": "x", "address": "0x0", "size": "0x100", "name": "X"},
            {"id": "x", "address": "0x200", "size": "0x100", "name": "X2"},
        ]}]}, f)
        f.close()
        errors = validate(f.name)
        self.assertTrue(any("duplicate" in e for e in errors))

    def test_same_section_id_in_different_views_is_valid(self):
        f = tempfile.NamedTemporaryFile(mode='w', suffix='.json',
                                        delete=False, encoding='utf-8')
        json.dump({"views": [
            {"id": "v1", "sections": [{"id": "flash", "address": "0x0", "size": "0x1000", "name": "Flash"}]},
            {"id": "v2", "sections": [{"id": "flash", "address": "0x0", "size": "0x1000", "name": "Flash"}]},
        ]}, f)
        f.close()
        errors = validate(f.name)
        self.assertEqual(errors, [])

    def test_duplicate_view_id_is_error(self):
        f = tempfile.NamedTemporaryFile(mode='w', suffix='.json',
                                        delete=False, encoding='utf-8')
        json.dump({"views": [
            {"id": "v", "sections": []},
            {"id": "v", "sections": []},
        ]}, f)
        f.close()
        errors = validate(f.name)
        self.assertTrue(any("duplicate" in e for e in errors))


class TestResolveViewSections(unittest.TestCase):

    def test_inline_section_parsed(self):
        result = resolve_view_sections({'sections': [
            {'id': 's1', 'address': '0x0', 'size': '0x1000', 'name': 'S1'}
        ]})
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].id, 's1')
        self.assertEqual(result[0].address, 0x0)
        self.assertEqual(result[0].size, 0x1000)
        self.assertEqual(result[0].name, 'S1')

    def test_flags_parsed(self):
        result = resolve_view_sections({'sections': [
            {'id': 's1', 'address': '0x0', 'size': '0x100',
             'name': 'S1', 'flags': ['grows-up']}
        ]})
        self.assertIn('grows-up', result[0].flags)

    def test_empty_sections_returns_empty(self):
        result = resolve_view_sections({'sections': []})
        self.assertEqual(result, [])

    def test_no_sections_key_returns_empty(self):
        result = resolve_view_sections({})
        self.assertEqual(result, [])

    def test_missing_id_skipped_with_warning(self):
        result = resolve_view_sections({'sections': [
            {'address': '0x0', 'size': '0x100', 'name': 'X'}
        ]})
        self.assertEqual(len(result), 0)

    def test_missing_address_skipped_with_warning(self):
        result = resolve_view_sections({'sections': [
            {'id': 'x', 'size': '0x100', 'name': 'X'}
        ]})
        self.assertEqual(len(result), 0)

    def test_missing_name_skipped_with_warning(self):
        result = resolve_view_sections({'sections': [
            {'id': 'x', 'address': '0x0', 'size': '0x100'}
        ]})
        self.assertEqual(len(result), 0)

    def test_multiple_sections_ordered(self):
        result = resolve_view_sections({'sections': [
            {'id': 'a', 'address': '0x0',    'size': '0x100', 'name': 'A'},
            {'id': 'b', 'address': '0x1000', 'size': '0x200', 'name': 'B'},
        ]})
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].id, 'a')
        self.assertEqual(result[1].id, 'b')

    def test_hex_address_normalized(self):
        result = resolve_view_sections({'sections': [
            {'id': 'flash', 'address': '0x08000000', 'size': '0x20000', 'name': 'Flash'}
        ]})
        self.assertEqual(result[0].address, 0x08000000)
        self.assertEqual(result[0].size, 0x20000)

    def test_min_height_parsed(self):
        result = resolve_view_sections({'sections': [
            {'id': 's', 'address': '0x0', 'size': '0x100', 'name': 'S', 'min_height': 30}
        ]})
        self.assertEqual(result[0].min_height, 30.0)

    def test_max_height_parsed(self):
        result = resolve_view_sections({'sections': [
            {'id': 's', 'address': '0x0', 'size': '0x100', 'name': 'S', 'max_height': 150}
        ]})
        self.assertEqual(result[0].max_height, 150.0)

    def test_min_max_height_defaults_none(self):
        result = resolve_view_sections({'sections': [
            {'id': 's', 'address': '0x0', 'size': '0x100', 'name': 'S'}
        ]})
        self.assertIsNone(result[0].min_height)
        self.assertIsNone(result[0].max_height)


class TestValidateDeprecated(unittest.TestCase):

    def test_diagram_size_produces_deprecation_warning(self):
        f = tempfile.NamedTemporaryFile(mode='w', suffix='.json',
                                        delete=False, encoding='utf-8')
        json.dump({"size": [500, 600], "views": []}, f)
        f.close()
        errors = validate(f.name)
        self.assertTrue(any("DEPRECATED" in e and "size" in e for e in errors))

    def test_view_pos_produces_deprecation_warning(self):
        f = tempfile.NamedTemporaryFile(mode='w', suffix='.json',
                                        delete=False, encoding='utf-8')
        json.dump({"views": [{"id": "v", "pos": [10, 20], "sections": []}]}, f)
        f.close()
        errors = validate(f.name)
        self.assertTrue(any("DEPRECATED" in e and "pos" in e for e in errors))

    def test_view_size_produces_deprecation_warning(self):
        f = tempfile.NamedTemporaryFile(mode='w', suffix='.json',
                                        delete=False, encoding='utf-8')
        json.dump({"views": [{"id": "v", "size": [100, 400], "sections": []}]}, f)
        f.close()
        errors = validate(f.name)
        self.assertTrue(any("DEPRECATED" in e and "size" in e for e in errors))

    def test_min_height_conflict_is_error(self):
        f = tempfile.NamedTemporaryFile(mode='w', suffix='.json',
                                        delete=False, encoding='utf-8')
        json.dump({"views": [{"id": "v", "sections": [
            {"id": "s", "address": "0x0", "size": "0x100", "name": "S",
             "min_height": 100, "max_height": 50}
        ]}]}, f)
        f.close()
        errors = validate(f.name)
        self.assertTrue(any("min_height" in e and "max_height" in e for e in errors))

    def test_min_height_negative_is_error(self):
        f = tempfile.NamedTemporaryFile(mode='w', suffix='.json',
                                        delete=False, encoding='utf-8')
        json.dump({"views": [{"id": "v", "sections": [
            {"id": "s", "address": "0x0", "size": "0x100", "name": "S",
             "min_height": -5}
        ]}]}, f)
        f.close()
        errors = validate(f.name)
        self.assertTrue(any("min_height" in e for e in errors))


if __name__ == '__main__':
    unittest.main()
