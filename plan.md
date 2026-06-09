1. **Create the search and replace widget**:
   - I have already created the `bookforge/gui/search_replace.py` with `SearchReplaceWidget` class.

2. **Integrate the widget into `MainWindow`**:
   - In `bookforge/gui/main_window.py` inside the `_center_panel` method, wrap the `latex_edit` in a layout that also contains the `SearchReplaceWidget`.
   - The `SearchReplaceWidget` should be initially hidden.
   - Add a keyboard shortcut (Ctrl+F) or a button/action to show the search and replace widget when the LaTeX tab is active.

3. **Pre-commit checks**:
   - Run tests using `pytest tests/` (or via `pre_commit_instructions`) to make sure I haven't broken anything.

4. **Submit**:
   - Commit and submit the changes.
