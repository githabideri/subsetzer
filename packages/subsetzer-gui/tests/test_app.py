import unittest
from unittest import mock

import subsetzer_gui.app as app_module


class GuiMainTests(unittest.TestCase):
    def test_main_exits_when_tk_missing(self):
        with mock.patch.object(app_module, "_TK_IMPORT_ERROR", Exception("no tk")), self.assertRaises(SystemExit) as ctx:
            app_module.main([])
        self.assertEqual(ctx.exception.code, 2)

    def test_main_runs_with_mock_tk(self):
        fake_root = mock.MagicMock()
        with mock.patch.object(app_module, "_TK_IMPORT_ERROR", None), mock.patch.object(
            app_module, "tk"
        ) as tk_mod, mock.patch.object(app_module, "App") as app_cls:
            tk_mod.Tk.return_value = fake_root
            app_instance = mock.MagicMock()
            app_cls.return_value = app_instance
            app_module.main([])
            tk_mod.Tk.assert_called_once()
            app_cls.assert_called_once()
            fake_root.mainloop.assert_called_once()

