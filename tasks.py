import curses
import json
from curses import wrapper
from curses.textpad import rectangle
from enum import Enum, auto

def sorts_saves_tasks(base_method):
    # Decorator: Enforces task priority (Active > Pending) and persists to disk
    def enhanced_method(self, *args, **kwargs):
        xReturn = base_method(self, *args, **kwargs)
        # Sort priority: Active tasks top, then Pending, then Finished
        self.list_dicts.sort(key=lambda Dict: (not Dict["active"], not Dict["pending"]))
        with open("tasks.json", "w") as f:
            json.dump(self.list_dicts, f)
        return xReturn
    return enhanced_method

class TaskManager:
    def __init__(self, max_active=3):
        self.MAX_ACTIVE = max_active
        self.list_dicts = self.load_tasks()
        self.current_active = self.enforce_max_active()
    def load_tasks(self):
        try:
            with open("tasks.json", "r") as f:
                list_dicts = json.load(f)
                
        except (FileNotFoundError, json.JSONDecodeError):
            list_dicts = []
        finally:
            
            return list_dicts

    def enforce_max_active(self):
        # Hard-caps active tasks and resets invalid active states (e.g. active but finished)
        current_active = 0
        changes = False
        for Dict in self.list_dicts:
            if (Dict["active"] and not Dict["pending"]):
                Dict["active"] = False
                if not changes: changes = True
            if Dict["active"] and Dict["pending"]: current_active += 1
            # Deactivate if over limit or if task was finished while active
            if current_active > self.MAX_ACTIVE and Dict["active"]:
                Dict["active"] = False
                current_active -= 1
                if not changes: changes = True
        if changes:
            self.list_dicts.sort(key=lambda Dict: (not Dict["active"], not Dict["pending"]))
            with open("tasks.json", "w") as f:
                json.dump(self.list_dicts, f)
        return current_active

    @sorts_saves_tasks
    def add_task(self, index, task_string):
        self.list_dicts.insert(index, {"task": task_string, "active": False, "pending": True})

    @sorts_saves_tasks
    def edit_task(self, index, task_string):
        self.list_dicts[index]["task"] = task_string

    @sorts_saves_tasks
    def delete_task(self, index):
        # Decrement counter if we are removing a task currently in an active focus slot
        if self.list_dicts[index]["active"]:
            self.current_active -= 1
        self.list_dicts.pop(index)

    @sorts_saves_tasks
    def toggle_pending(self, index):
        # Toggles completion. Auto-deactivates if marking as finished
        if self.list_dicts[index]["active"]:
            self.list_dicts[index]["active"] = False
            self.current_active -= 1
        self.list_dicts[index]["pending"] = not self.list_dicts[index]["pending"]

    @sorts_saves_tasks
    def toggle_active(self, index):
        self.list_dicts[index]["active"] = not self.list_dicts[index]["active"]
        self.current_active += 1 if self.list_dicts[index]["active"] else -1

    def get_tasks(self): return self.list_dicts
    def get_count(self): return len(self.list_dicts)
    def get_task_at(self, index): return self.list_dicts[index]

class Execution(Enum):
    ADD = auto()
    EDIT = auto()
    DELETE = auto()
    PENDING = auto()
    ACTIVE = auto()
    QUIT = auto()
    EXIT_APP = auto()

class input_state(Enum):
    POSITION = auto()
    EXECUTE = auto()
    STRING = auto()

class invalid_index(Exception): pass

def main(stdscr):
    # Global TUI styling and state initialization
    curses.init_pair(1, curses.COLOR_GREEN, curses.COLOR_BLACK)
    GREEN_TEXT = curses.color_pair(1)
    stdscr.attron(GREEN_TEXT)

    app = tasks_app(stdscr, GREEN_TEXT, MAX_ACTIVE=3)
    app.run()
    stdscr.attroff(GREEN_TEXT)

class tasks_app:
    def __init__(self, stdscr, GREEN_TEXT, MAX_ACTIVE=3):
        self.stdscr = stdscr
        self.GREEN_TEXT = GREEN_TEXT
        self.manager = TaskManager(max_active=MAX_ACTIVE)
        self.terminal_height, self.terminal_width = self.stdscr.getmaxyx()
        
        # Opcodes for action routing
        self.ADD_CHAR, self.EDIT_CHAR, self.DELETE_CHAR = "a", "e", "d"
        self.PENDING_CHAR, self.ACTIVE_CHAR, self.QUIT_CHAR = "f", "p", "q"
        self.EXIT_STR = "none"

        # Layout Geometry
        self.ACTIVE_MARK_X, self.HEADER_Y, self.PAD_START_Y, self.INFO_PROMPTS_HEIGHT = 1, 0, 2, 6
        self.INDEX_START_X = self.ACTIVE_MARK_X + 3
        self.EMPTY_PROMPT = "(No tasks exist)"

        self.left_margin = 6 + len(str(self.manager.get_count()))
        self.rework_windows = False

        self.INFO_PROMPTS_START_Y = min(self.manager.get_count() + self.PAD_START_Y + 2, self.terminal_height - self.INFO_PROMPTS_HEIGHT)
        
        # Primary Windows: Main UI container, Task Pad, and Input Field
        #in testing, I've found that windows need a buffer space of 2 columns horizontally but only one row vertically
        self.tasks_ui_window = curses.newwin(self.terminal_height, 
                                             self.terminal_width, 0, 0)
        self.tasks_ui_window.attron(GREEN_TEXT)
        self.tasks_pad = curses.newpad(max(1000, self.manager.get_count() * 2), 1000)

        #3 tasks lines + 1 for rectangle + 1 for gap = 5
        self.APP_MINIMUM_HEIGHT = self.PAD_START_Y + self.INFO_PROMPTS_HEIGHT + 5
        #calculated before hand. Value subject to change as app develops
        self.APP_MINIMUM_WIDTH = 55

        self.input_state = input_state.POSITION

        self.tasks_ui_window.keypad(True)

    def run(self):
        while True:
            self.render_frame()
            execution, int_index, mod_task = self.process_interaction()
            if execution == Execution.EXIT_APP: break
            if execution: self.process_execution(execution, int_index, mod_task)

    def printstr(self, window, string, y = None, x = None, style = None):
        window_height, window_width = window.getmaxyx()
        
        # Boundary check to prevent crashes on small terminal heights
        if y is not None and (y < 0 or y >= window_height):
            return

        if window is self.tasks_pad:
            available_space = self.terminal_width - self.left_margin - 2
        else:
            if y is not None and x is not None: cursor_y, cursor_x = y, x
            else: cursor_y, cursor_x = window.getyx()
            available_space = window_width - cursor_x

        if available_space <= 0: return
        elif available_space < 3 and len(string) >= available_space: string = "." * available_space
        elif len(string) > available_space:
            string = string[:available_space - 3] + "..."

        try:
            if (y is not None and x is not None) and style is not None: window.addstr(y, x, string, style)
            elif (y is not None and x is not None): window.addstr(y, x, string)
            elif style is not None: window.addstr(string, style)
            else: window.addstr(string)
        except curses.error:
            cur_y, _ = window.getyx()
            if cur_y < window_height - 1: raise
            else: pass

    def print_input(self, window, string, available_space, string_view_start = None, style = None):
        if available_space <= 0: return
        if string_view_start is None: string_view_start = max(len(string) - available_space, 0)
        if string_view_start > 0: display_string = window.addch("<", curses.A_REVERSE)
        else: window.addch(" ")
        
        display_string = string[string_view_start: string_view_start + available_space]
        if style is not None: window.addstr(display_string, style)
        else: window.addstr(display_string)

        if string_view_start + available_space < len(string): window.addch(">", curses.A_REVERSE)

    def render_frame(self, execution = None, int_human_index = None):
        cursor_hidden = False
        while self.terminal_height < self.APP_MINIMUM_HEIGHT or self.terminal_width < self.APP_MINIMUM_WIDTH:
            if not cursor_hidden: curses.curs_set(0); cursor_hidden = True
            self.screen_size_warning()
        if cursor_hidden: curses.curs_set(1); cursor_hidden = False

        list_dicts = self.manager.get_tasks()
        number_of_tasks = self.manager.get_count()
        self.left_margin = 6 + len(str(self.manager.get_count()))
        
        self.render_ui_elements(number_of_tasks)
        self.tasks_pad.erase()

        if list_dicts:
            self.printstr(self.tasks_ui_window, "tasks:", self.HEADER_Y, self.left_margin, self.GREEN_TEXT | curses.A_BOLD)
            for index, Dict in enumerate(list_dicts):
                if Dict["active"]:
                    self.printstr(self.tasks_ui_window, "*", index + self.PAD_START_Y, self.ACTIVE_MARK_X)
                style = self.GREEN_TEXT if Dict["pending"] else curses.A_DIM
                if index + 1 < min(number_of_tasks + self.PAD_START_Y - 1, self.terminal_height - self.INFO_PROMPTS_HEIGHT - 3):
                    self.printstr(self.tasks_ui_window, f"{index + 1}", index + self.PAD_START_Y, self.INDEX_START_X, style)
                self.printstr(self.tasks_pad, f"{Dict['task']}", index, 0, style)

            self.tasks_ui_window.noutrefresh()
            # Dynamic viewport calculation for Pad rendering within screen boundaries
            self.tasks_pad.noutrefresh(0, 0, self.PAD_START_Y, self.left_margin,
                min(number_of_tasks + self.PAD_START_Y - 1, self.terminal_height - self.INFO_PROMPTS_HEIGHT - 3), self.terminal_width - 3)
        else:
            self.printstr(self.tasks_ui_window, "tasks:", self.HEADER_Y, self.left_margin, self.GREEN_TEXT | curses.A_BOLD)
            self.printstr(self.tasks_ui_window, self.EMPTY_PROMPT, self.PAD_START_Y, self.left_margin)
            self.tasks_ui_window.noutrefresh()
        if self.input_state == input_state.POSITION: self.position_prompt()
        if int_human_index is not None:
            if execution is not None: self.task_string_prompt(execution, int_human_index)
            else: self.execution_prompt(int_human_index)

        curses.doupdate()

    def render_ui_elements(self, number_of_tasks):
        # Handles Dynamic Window Scaling and UI container rectangles
        self.tasks_ui_window.erase()

        if number_of_tasks > 0:
            if self.rework_windows:
                self.INFO_PROMPTS_START_Y = min(number_of_tasks + self.PAD_START_Y + 2, self.terminal_height - self.INFO_PROMPTS_HEIGHT)
                self.tasks_ui_window.resize(self.terminal_height, self.terminal_width)
                self.rework_windows = False

            # Draw Focus box for active items and Main Container for the list
            if 0 < self.manager.current_active <= self.manager.MAX_ACTIVE:
                rectangle(self.tasks_ui_window, self.PAD_START_Y - 1, self.ACTIVE_MARK_X - 1,
                        self.manager.current_active + self.PAD_START_Y, self.ACTIVE_MARK_X + 1)    
            rectangle(self.tasks_ui_window, self.PAD_START_Y - 1, self.INDEX_START_X - 1,
                    min(self.PAD_START_Y + number_of_tasks, self.terminal_height - self.INFO_PROMPTS_HEIGHT - 2),
                    self.INDEX_START_X + len(str(number_of_tasks)))
            rectangle(self.tasks_ui_window, self.PAD_START_Y - 1, self.left_margin - 1,
                    min(self.PAD_START_Y + number_of_tasks, self.terminal_height - self.INFO_PROMPTS_HEIGHT - 2), self.terminal_width - 2)
        else:
            self.INFO_PROMPTS_START_Y = self.PAD_START_Y + 2
            self.tasks_ui_window.resize(self.terminal_height, self.terminal_width)
        
        self.tasks_ui_window.noutrefresh()

    def screen_size_warning(self):
        self.tasks_ui_window.erase()
            
        if self.terminal_height < self.APP_MINIMUM_HEIGHT and self.terminal_width < self.APP_MINIMUM_WIDTH: msg = "Terminal too small!"
        elif self.terminal_height < self.APP_MINIMUM_HEIGHT: msg = "Terminal too short!"
        else: msg = "Terminal too narrow!"

        # Center the message roughly
        self.printstr(self.tasks_ui_window, msg, self.terminal_height // 2, max(0, (self.terminal_width - len(msg)) // 2), self.GREEN_TEXT | curses.A_REVERSE)
        self.tasks_ui_window.refresh()
        ch = self.tasks_ui_window.getch()
        if ch == curses.KEY_RESIZE: 
            self.terminal_height, self.terminal_width = self.stdscr.getmaxyx()
            if not self.rework_windows: self.rework_windows = True
    
    def resize_updates(self, execution = None, int_human_index = None):
        self.terminal_height, self.terminal_width = self.stdscr.getmaxyx()
        self.render_frame(execution, int_human_index)

    def position_prompt(self):
        if self.input_state != input_state.POSITION: self.input_state = input_state.POSITION
        position_prompt = "Which position would you like to modify:"
        self.printstr(self.tasks_ui_window, position_prompt, self.INFO_PROMPTS_START_Y, self.INDEX_START_X); self.tasks_ui_window.clrtobot()
        self.printstr(self.tasks_ui_window, f"Enter '{self.EXIT_STR}' or '0' to exit.", self.INFO_PROMPTS_START_Y + 1, self.INDEX_START_X)
        self.printstr(self.tasks_ui_window, "Use '+' to append a new task.", self.INFO_PROMPTS_START_Y + 2, self.INDEX_START_X)
        self.printstr(self.tasks_ui_window, "Grey tasks = Finished", self.INFO_PROMPTS_START_Y + 3, self.INDEX_START_X, curses.A_DIM)
        
        if self.manager.current_active > 0:    
            rectangle(self.tasks_ui_window, self.INFO_PROMPTS_START_Y + 3, self.ACTIVE_MARK_X - 1, self.INFO_PROMPTS_START_Y + 5, self.ACTIVE_MARK_X + 1)
            self.printstr(self.tasks_ui_window, "*", self.INFO_PROMPTS_START_Y + 4, self.ACTIVE_MARK_X)
            self.printstr(self.tasks_ui_window, f"Active focus slots: {self.manager.current_active}/{self.manager.MAX_ACTIVE}",
                          self.INFO_PROMPTS_START_Y + 4, self.INDEX_START_X)

        #moves the cursor
        self.tasks_ui_window.move(self.INFO_PROMPTS_START_Y + 0, self.INDEX_START_X + len(position_prompt))
        self.tasks_ui_window.refresh()
        
    def execution_prompt(self, int_human_index):
        if self.input_state != input_state.EXECUTE: self.input_state = input_state.EXECUTE
        Dict = self.manager.get_task_at(int_human_index - 1)
        self.printstr(self.tasks_ui_window, f"Position: {int_human_index}", self.INFO_PROMPTS_START_Y, self.INDEX_START_X); self.tasks_ui_window.clrtobot()
        self.printstr(self.tasks_ui_window, f"({self.ADD_CHAR})Add ({self.EDIT_CHAR})Edit ({self.DELETE_CHAR})Del ({self.QUIT_CHAR})Cancel",
                      self.INFO_PROMPTS_START_Y + 1, self.INDEX_START_X)
        self.printstr(self.tasks_ui_window, f"({self.ACTIVE_CHAR})Toggle Active ({self.PENDING_CHAR})Toggle Finish",
                      self.INFO_PROMPTS_START_Y + 2, self.INDEX_START_X)
        
        if not Dict["pending"]:
            self.printstr(self.tasks_ui_window, "Finished tasks cannot be active focus.", self.INFO_PROMPTS_START_Y + 4, self.ACTIVE_MARK_X, curses.A_DIM)
        
        self.tasks_ui_window.refresh()

    def task_string_prompt(self, execution, int_human_index):
        if self.input_state != input_state.STRING: self.input_state = input_state.STRING
        choosen_execution = "task" if execution == Execution.ADD else "edit"
        self.printstr(self.tasks_ui_window, f"Position: {int_human_index}", self.INFO_PROMPTS_START_Y, self.INDEX_START_X); self.tasks_ui_window.clrtobot()
        self.printstr(self.tasks_ui_window, f"{choosen_execution}:", self.INFO_PROMPTS_START_Y + 1, self.INDEX_START_X)
        self.tasks_ui_window.refresh()

    def get_string(self, window, execution = None, int_human_index = None, buffer = ""):
        original_y, original_x = window.getyx()
        _, max_x = window.getmaxyx()
        
        available_space = max(max_x - original_x - 3, 0)
        
        buffer_view_start, buffer_cursor_pos = 0, len(buffer)

        while True:
            if buffer_cursor_pos >= buffer_view_start + available_space:
                buffer_view_start = buffer_cursor_pos - available_space + 1
            
            if buffer_cursor_pos < buffer_view_start:
                buffer_view_start = buffer_cursor_pos

            window.move(original_y, original_x); window.clrtoeol()
            self.print_input(window, buffer, available_space, buffer_view_start)
            
            window.move(original_y, original_x + 1 + (buffer_cursor_pos - buffer_view_start))
            window.refresh()

            char_code = window.getch()

            if char_code in (10, 13): # Enter
                break
                
            elif char_code == curses.KEY_RESIZE:
                self.rework_windows = True
                self.resize_updates(execution, int_human_index) 
                original_y, original_x = window.getyx()
                _, max_x = window.getmaxyx()
                available_space = max(max_x - original_x - 3, 0)

            elif char_code == curses.KEY_LEFT: 
                if buffer_cursor_pos > 0:
                    buffer_cursor_pos -= 1

            elif char_code == curses.KEY_RIGHT: 
                if buffer_cursor_pos < len(buffer):
                    buffer_cursor_pos += 1

            elif char_code in (curses.KEY_BACKSPACE, 127, 8):
                if buffer_cursor_pos > 0:
                    buffer = buffer[:buffer_cursor_pos - 1] + buffer[buffer_cursor_pos:]
                    buffer_cursor_pos -= 1

            elif char_code == curses.KEY_DC: # Delete Key
                if buffer_cursor_pos < len(buffer):
                    buffer = buffer[:buffer_cursor_pos] + buffer[buffer_cursor_pos + 1:]

            elif 32 <= char_code <= 126: # Standard Characters
                char = chr(char_code)
                buffer = buffer[:buffer_cursor_pos] + char + buffer[buffer_cursor_pos:]
                buffer_cursor_pos += 1

        return buffer
    
    def get_execution(self, window, int_human_index = None):
        while True:
            char_code = window.getch()
            if char_code == curses.KEY_RESIZE: self.rework_windows = True; self.resize_updates(None, int_human_index)
            else:
                ch = chr(char_code).lower()
                match ch:
                    case self.ADD_CHAR: execution = Execution.ADD; break
                    case self.EDIT_CHAR: execution = Execution.EDIT; break
                    case self.DELETE_CHAR: execution = Execution.DELETE; break
                    case self.PENDING_CHAR: execution = Execution.PENDING; break
                    case self.ACTIVE_CHAR: execution = Execution.ACTIVE; break
                    case self.QUIT_CHAR: execution = Execution.QUIT; break
                    case _: continue
        return execution
    
    def process_interaction(self):
        if self.input_state != input_state.POSITION: self.position_prompt()
        human_index = self.get_string(self.tasks_ui_window).strip()
        if human_index.lower() in (self.EXIT_STR, "0"): return Execution.EXIT_APP, None, None
        try:
            # Route '+' or index to the appropriate logic position
            int_human_index = self.manager.get_count() + 1 if human_index == "+" else int(human_index)
            if not (0 < int_human_index <= self.manager.get_count() + 1): raise invalid_index
        except (invalid_index, ValueError): return None, None, None
        
        while True:
            # Auto-routing: Brim selection defaults to Add; existing index prompts for action
            if int_human_index == self.manager.get_count() + 1: execution = Execution.ADD
            else: 
                self.execution_prompt(int_human_index)
                curses.curs_set(0)
                execution = self.get_execution(self.tasks_ui_window, int_human_index)
                curses.curs_set(1)
            
            match execution:
                case Execution.QUIT: return None, None, None
                case Execution.DELETE | Execution.PENDING: return execution, int_human_index - 1, None
                case Execution.ACTIVE:
                    target_task = self.manager.get_task_at(int_human_index - 1)
                    # Constraint: Prevent activation if finished or focus slots are full
                    if (self.manager.current_active == self.manager.MAX_ACTIVE and not target_task["active"]) or not target_task["pending"]:
                        continue
                    return execution, int_human_index - 1, None
                case Execution.ADD | Execution.EDIT:
                    if execution == Execution.EDIT: task_string = self.manager.get_task_at(int_human_index - 1)["task"]
                    else: task_string = ""
                    self.task_string_prompt(execution, int_human_index,)
                    while True:
                        if (task_string := self.get_string(self.tasks_ui_window, execution, int_human_index, task_string).strip()): break
                    return execution, int_human_index - 1, task_string
                case _: continue

    def process_execution(self, execution, int_index, mod_task = None):
        match execution:
            case Execution.ADD:
                self.manager.add_task(int_index, mod_task)
                self.rework_windows = True
            case Execution.EDIT:
                self.manager.edit_task(int_index, mod_task)
            case Execution.DELETE:
                self.manager.delete_task(int_index)
                self.rework_windows = True
            case Execution.PENDING: self.manager.toggle_pending(int_index)
            case Execution.ACTIVE: self.manager.toggle_active(int_index)

if __name__ == "__main__":
    # Standard curses wrapper handles terminal initialisation and cleanup
    wrapper(main)