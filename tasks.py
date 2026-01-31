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
        self.current_active, self.current_pending = self.enforce_max_active()
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
        current_active, current_pending, changes = 0, 0, False
        for Dict in self.list_dicts:
            if Dict["pending"]: current_pending += 1
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
        return current_active, current_pending

    @sorts_saves_tasks
    def add_task(self, index, task_string):
        self.list_dicts.insert(index, {"task": task_string, "active": False, "pending": True})
        self.current_pending += 1

    @sorts_saves_tasks
    def edit_task(self, index, task_string):
        self.list_dicts[index]["task"] = task_string

    @sorts_saves_tasks
    def delete_task(self, index):
        # Decrement counter if we are removing a task currently in an active focus slot
        if self.list_dicts[index]["active"]: self.current_active -= 1
        if self.list_dicts[index]["pending"]: self.current_pending -= 1
        self.list_dicts.pop(index)

    @sorts_saves_tasks
    def toggle_pending(self, index):
        # Toggles completion. Auto-deactivates if marking as finished
        if self.list_dicts[index]["active"]:
            self.list_dicts[index]["active"] = False
            self.current_active -= 1
        self.list_dicts[index]["pending"] = not self.list_dicts[index]["pending"]
        self.current_pending += 1 if self.list_dicts[index]["pending"] else -1

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
class colour_error(Exception): pass

def main(stdscr):
    curses.start_color()
    curses.set_escdelay(25)
    try: 
        if curses.COLORS < 256: raise colour_error
    except colour_error:
        error_msgs = [" [!] INCOMPATIBLE TERMINAL [!]",
                      " This app requires 256-color support.",
                      f" Your current terminal ({curses.termname().decode()}) only supports {curses.COLORS} colors."]
        return error_msgs

    app = tasks_app(stdscr, MAX_ACTIVE=3)
    app.run()
    return None

class tasks_app:
    def __init__(self, stdscr, MAX_ACTIVE=3):
        self.stdscr = stdscr
        self.manager = TaskManager(max_active=MAX_ACTIVE)
        self.terminal_height, self.terminal_width = self.stdscr.getmaxyx()
        
        # Opcodes for action routing
        self.ADD_CHAR, self.EDIT_CHAR, self.DELETE_CHAR = "a", "e", "d"
        self.PENDING_CHAR, self.ACTIVE_CHAR, self.QUIT_CHAR = "f", "p", "q"

        # Layout Geometry
        self.ACTIVE_MARK_X, self.HEADER_Y, self.PAD_START_Y, self.INFO_PROMPTS_HEIGHT = 1, 0, 2, 7
        self.INDEX_START_X = self.ACTIVE_MARK_X + 3

        self.left_margin = 6 + len(str(self.manager.get_count()))
        self.rework_windows = False
        self.highlighted_task_index = None

        self.INFO_PROMPTS_START_Y = min(self.manager.get_count() + self.PAD_START_Y + 2, self.terminal_height - self.INFO_PROMPTS_HEIGHT)
        
        # Primary Windows: Main UI container, Task Pad, and Input Field
        #in testing, I've found that windows need a buffer space of 2 columns horizontally but only one row vertically
        self.tasks_ui_window = curses.newwin(self.terminal_height, 
                                             self.terminal_width, 0, 0)
        self.tasks_pad = curses.newpad(max(1000, self.manager.get_count() * 2), 1000)

        #3 tasks lines + 1 for rectangle + 1 for gap = 5
        self.APP_MINIMUM_HEIGHT = self.PAD_START_Y + self.INFO_PROMPTS_HEIGHT + 5
        #calculated before hand. Value subject to change as app develops
        self.APP_MINIMUM_WIDTH = 55

        self.input_state = input_state.POSITION

        self.tasks_ui_window.keypad(True)

        curses.init_pair(1, curses.COLOR_GREEN, 234)
        curses.init_pair(2, curses.COLOR_GREEN, 235)
        curses.init_pair(3, curses.COLOR_WHITE, 234)
        curses.init_pair(4, curses.COLOR_WHITE, 235)
        self.GREEN_TEXT = curses.color_pair(1)
        self.GREEN_TEXT_ALT = curses.color_pair(2)
        self.FINISHED_TEXT = curses.color_pair(3) | curses.A_DIM
        self.FINISHED_TEXT_ALT = curses.color_pair(4) | curses.A_DIM

        self.tasks_ui_window.attron(self.GREEN_TEXT)

    def run(self):
        while True:
            if self.input_state != input_state.POSITION: self.input_state = input_state.POSITION
            self.render_frame()
            execution, mod_task = self.process_interaction()
            if execution == Execution.EXIT_APP: break
            if execution: self.process_execution(execution, mod_task)

    def printstr(self, window, string, y = None, x = None, style = None):
        window_height, window_width = window.getmaxyx()
        display_string = string
        # Boundary check to prevent crashes on small terminal heights
        if y is not None and (y < 0 or y >= window_height): return

        if window is self.tasks_pad:
            available_space = self.terminal_width - self.left_margin - 2
        else:
            if y is not None and x is not None: _, cursor_x = y, x
            else: _, cursor_x = window.getyx()
            available_space = window_width - cursor_x

        if available_space <= 0: return
        elif available_space < 3 and len(string) >= available_space: display_string = "." * available_space
        elif len(string) > available_space:
            display_string = string[:available_space - 3] + "..."
        elif window is self.tasks_pad: display_string = string + " " * (available_space - len(string))

        try:
            if (y is not None and x is not None) and style is not None: window.addstr(y, x, display_string, style)
            elif (y is not None and x is not None): window.addstr(y, x, display_string)
            elif style is not None: window.addstr(display_string, style)
            else: window.addstr(display_string)
        except curses.error:
            #somewhat problematic solution to crashes on miniscule terminal sizes
            #problem is it will pass any and all errors as long y coordinate of y is less than height of window
            cur_y, _ = window.getyx()
            if cur_y < window_height - 1: raise
            else: pass

    def print_input(self, window, string, available_space, string_view_start = None, style = None):
        if available_space <= 0: return
        if string_view_start is None: string_view_start = max(len(string) - available_space, 0)
        if string_view_start > 0: window.addch("<", curses.A_REVERSE)
        else: window.addch(" ")
        
        display_string = string[string_view_start: string_view_start + available_space]

        try:
            if style is not None: window.addstr(display_string, style)
            else: window.addstr(display_string)
        except curses.error:
            window_height, _ = window.getmaxyx()
            cur_y, _ = window.getyx()
            if cur_y < window_height - 1: raise
            else: pass

        if string_view_start + available_space < len(string): window.addch(">", curses.A_REVERSE)#display_string = display_string[:-1] + ">" 

    def render_frame(self, execution = None):
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
                if Dict["pending"]: style = self.GREEN_TEXT if index % 2 == 0 else self.GREEN_TEXT_ALT
                else: style = self.FINISHED_TEXT if index % 2 == 0 else self.FINISHED_TEXT_ALT
                if index == self.highlighted_task_index: style = style | curses.A_REVERSE
                if index + 1 < min(number_of_tasks + self.PAD_START_Y - 1, self.terminal_height - self.INFO_PROMPTS_HEIGHT - 3):
                    index_margin = " " * (len(str(number_of_tasks)) - len(str(index + 1))) if len(str(index + 1)) < len(str(number_of_tasks)) else ""
                    self.printstr(self.tasks_ui_window, f"{index_margin}{index + 1}", index + self.PAD_START_Y, self.INDEX_START_X, style)
                self.printstr(self.tasks_pad, f"{Dict['task']}", index, 0, style)

            self.tasks_ui_window.noutrefresh()
            # Dynamic viewport calculation for Pad rendering within screen boundaries
            self.tasks_pad.noutrefresh(0, 0, self.PAD_START_Y, self.left_margin,
                min(number_of_tasks + self.PAD_START_Y - 1, self.terminal_height - self.INFO_PROMPTS_HEIGHT - 3), self.terminal_width - 3)
        else:
            self.printstr(self.tasks_ui_window, "tasks:", self.HEADER_Y, self.left_margin, self.GREEN_TEXT | curses.A_BOLD)
            style = self.GREEN_TEXT | curses.A_REVERSE if self.highlighted_task_index == 0 else self.GREEN_TEXT
            self.printstr(self.tasks_ui_window, "(No tasks exist)", self.PAD_START_Y, self.left_margin, style)
            self.tasks_ui_window.noutrefresh()
        match self.input_state:
            case input_state.POSITION: self.position_prompt()
            case input_state.EXECUTE: self.execution_prompt()
            case input_state.STRING: self.task_string_prompt(execution)

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
    
    def resize_updates(self, execution = None):
        self.terminal_height, self.terminal_width = self.stdscr.getmaxyx()
        self.render_frame(execution)

    def position_prompt(self):
        if self.input_state != input_state.POSITION: self.input_state = input_state.POSITION
        self.printstr(self.tasks_ui_window, "Select a position to modify", self.INFO_PROMPTS_START_Y, self.INDEX_START_X); self.tasks_ui_window.clrtobot()
        self.printstr(self.tasks_ui_window, f"Hit 'q', 'Esc', or '0' to exit.", self.INFO_PROMPTS_START_Y + 1, self.INDEX_START_X)
        self.printstr(self.tasks_ui_window, "Hit '+' to append a new task.", self.INFO_PROMPTS_START_Y + 2, self.INDEX_START_X)
        self.printstr(self.tasks_ui_window, "Grey tasks = Finished", self.INFO_PROMPTS_START_Y + 3, self.INDEX_START_X, self.FINISHED_TEXT)
        self.printstr(self.tasks_ui_window, "Finished tasks cannot have active focus.", self.INFO_PROMPTS_START_Y + 4, self.INDEX_START_X, self.FINISHED_TEXT)
        
        if self.manager.current_active > 0:    
            rectangle(self.tasks_ui_window, self.INFO_PROMPTS_START_Y + 4, self.ACTIVE_MARK_X - 1, self.INFO_PROMPTS_START_Y + 6, self.ACTIVE_MARK_X + 1)
            self.printstr(self.tasks_ui_window, "*", self.INFO_PROMPTS_START_Y + 5, self.ACTIVE_MARK_X)
            self.printstr(self.tasks_ui_window, f"Active focus slots: {self.manager.current_active}/{self.manager.MAX_ACTIVE}",
                          self.INFO_PROMPTS_START_Y + 5, self.INDEX_START_X)

        self.tasks_ui_window.refresh()
        
    def execution_prompt(self, highlighted_execution = None):
        if self.input_state != input_state.EXECUTE: self.input_state = input_state.EXECUTE
        executions_texts = ["ADD", "EDIT", "TOGGLE ACTIVE", "TOGGLE FINISHED", "DELETE", "CANCEL"]
        self.printstr(self.tasks_ui_window, f"Position: {self.highlighted_task_index + 1}", self.INFO_PROMPTS_START_Y, self.INDEX_START_X); self.tasks_ui_window.clrtobot()

        for index, execution in enumerate(executions_texts, start = 1):
            style = self.GREEN_TEXT | curses.A_REVERSE if highlighted_execution == index else self.GREEN_TEXT
            if index == 3:
                target_task = self.manager.get_task_at(self.highlighted_task_index)
                # greys out "toggle active" when necessary
                if (self.manager.current_active == self.manager.MAX_ACTIVE and not target_task["active"]) or not target_task["pending"]:
                    style = self.FINISHED_TEXT | curses.A_REVERSE if highlighted_execution == index else self.FINISHED_TEXT 
            self.printstr(self.tasks_ui_window, execution, self.INFO_PROMPTS_START_Y + index, self.INDEX_START_X, style)

        self.tasks_ui_window.refresh()

    def task_string_prompt(self, execution):
        if self.input_state != input_state.STRING: self.input_state = input_state.STRING
        choosen_execution = "task" if execution == Execution.ADD else "edit"
        self.printstr(self.tasks_ui_window, f"Position: {self.highlighted_task_index + 1}", self.INFO_PROMPTS_START_Y, self.INDEX_START_X); self.tasks_ui_window.clrtobot()
        self.printstr(self.tasks_ui_window, f"{choosen_execution}:", self.INFO_PROMPTS_START_Y + 1, self.INDEX_START_X)
        self.tasks_ui_window.refresh()

    def tasks_navigation(self, window, execution = None):
        curses.curs_set(0)
        while True:
            char_code = window.getch()
            match char_code:
                case code if code == ord("q") or code == ord("Q") or code == ord("0") or code == 27: self.highlighted_task_index = -1; break # 27 = Esc
                case 10 | 13: 
                    if self.highlighted_task_index is not None: break
                case code if code == ord("+"): 
                    self.highlighted_task_index = self.manager.get_count(); break
                case curses.KEY_RESIZE:
                    self.rework_windows = True
                    self.resize_updates(execution)
                case curses.KEY_UP:
                    if self.highlighted_task_index is None or not self.highlighted_task_index > 0: self.highlighted_task_index = self.manager.get_count()
                    else: self.highlighted_task_index -= 1
                case curses.KEY_DOWN:
                    if self.highlighted_task_index is None or not self.highlighted_task_index < self.manager.get_count(): self.highlighted_task_index = 0
                    else: self.highlighted_task_index += 1
                case _: continue
            self.render_frame(execution)
        curses.curs_set(1)
    
    def get_string(self, window, execution = None, buffer = "", style = None):
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
            self.print_input(window, buffer, available_space, buffer_view_start, style)
            
            window.move(original_y, original_x + 1 + (buffer_cursor_pos - buffer_view_start))
            window.refresh()

            char_code = window.getch()

            match char_code:
                case 10 | 13: break #Enter key
                case curses.KEY_RESIZE:
                    self.rework_windows = True
                    self.resize_updates(execution) 
                    original_y, original_x = window.getyx()
                    _, max_x = window.getmaxyx()
                    available_space = max(max_x - original_x - 3, 0)
                case curses.KEY_LEFT: 
                    if buffer_cursor_pos > 0:
                        buffer_cursor_pos -= 1
                case curses.KEY_RIGHT: 
                    if buffer_cursor_pos < len(buffer):
                        buffer_cursor_pos += 1
                case curses.KEY_BACKSPACE | 127 | 8:
                    if buffer_cursor_pos > 0:
                        buffer = buffer[:buffer_cursor_pos - 1] + buffer[buffer_cursor_pos:]
                        buffer_cursor_pos -= 1
                case curses.KEY_DC: # Delete Key
                    if buffer_cursor_pos < len(buffer):
                        buffer = buffer[:buffer_cursor_pos] + buffer[buffer_cursor_pos + 1:]
                case curses.KEY_HOME: buffer_cursor_pos = 0
                case curses.KEY_END: buffer_cursor_pos = len(buffer)
                case code if 32 <= code <= 126: # Standard Characters
                    char = chr(char_code)
                    buffer = buffer[:buffer_cursor_pos] + char + buffer[buffer_cursor_pos:]
                    buffer_cursor_pos += 1

        return buffer
    
    def get_execution(self, window):
        curses.curs_set(0)
        highlighted_execution = None
        while True:
            char_code = window.getch()
            match char_code:
                case code if code == ord("q") or code == ord("Q") or code == ord("0") or code == 27:
                    curses.curs_set(1); return Execution.QUIT
                case 10 | 13: #enter key
                    if highlighted_execution is not None:
                        if highlighted_execution == 3:
                            target_task = self.manager.get_task_at(self.highlighted_task_index)
                            # Constraint: Prevent activation if finished or focus slots are full
                            if (self.manager.current_active == self.manager.MAX_ACTIVE and not target_task["active"]) or not target_task["pending"]:
                                continue
                        break
                case curses.KEY_RESIZE: self.rework_windows = True; self.resize_updates()
                case curses.KEY_UP:
                    if highlighted_execution is None or not highlighted_execution > 1: highlighted_execution = 6
                    else: highlighted_execution -= 1
                case curses.KEY_DOWN:
                    if highlighted_execution is None or not highlighted_execution < 6: highlighted_execution = 1
                    else: highlighted_execution += 1
                case _: continue
            self.execution_prompt(highlighted_execution)
        curses.curs_set(1)
        match highlighted_execution:
            case 1: return Execution.ADD
            case 2: return Execution.EDIT
            case 3: return Execution.ACTIVE
            case 4: return Execution.PENDING
            case 5: return Execution.DELETE
            case 6: return Execution.QUIT
    
    def process_interaction(self):
        if self.input_state != input_state.POSITION: self.position_prompt()
        self.tasks_navigation(self.tasks_ui_window)
        if self.highlighted_task_index == -1: return Execution.EXIT_APP, None
        
        while True:
            # Auto-routing: Brim selection defaults to Add; existing index prompts for action
            if self.highlighted_task_index == self.manager.get_count():
                self.highlighted_task_index = self.manager.current_pending
                self.render_frame()
                execution = Execution.ADD
            else: 
                self.execution_prompt()
                execution = self.get_execution(self.tasks_ui_window)
            
            match execution:
                case Execution.QUIT: return None, None
                case Execution.DELETE | Execution.PENDING: return execution, None
                case Execution.ACTIVE:
                    return execution, None
                case Execution.ADD | Execution.EDIT:
                    if execution == Execution.EDIT: task_string = self.manager.get_task_at(self.highlighted_task_index)["task"]
                    else: task_string = ""
                    self.task_string_prompt(execution)
                    style = self.FINISHED_TEXT if execution == Execution.EDIT and not self.manager.get_task_at(self.highlighted_task_index)["pending"] else None
                    #need these to counter a bug
                    cursor_y, cursor_x = self.tasks_ui_window.getyx()
                    while True:
                        #print_input adds a " ", this stops that from compounding when empty strings get returned
                        self.tasks_ui_window.move(cursor_y, cursor_x)
                        if (task_string := self.get_string(self.tasks_ui_window, execution, task_string, style).strip()): break
                    return execution, task_string
                case _: continue

    def process_execution(self, execution, mod_task = None):
        # Bridges UI intent to Model logic and updates layout dimensions if needed
        match execution:
            case Execution.ADD:
                self.manager.add_task(self.highlighted_task_index, mod_task)
                self.rework_windows = True
            case Execution.EDIT:
                self.manager.edit_task(self.highlighted_task_index, mod_task)
            case Execution.DELETE:
                self.manager.delete_task(self.highlighted_task_index)
                self.rework_windows = True
            case Execution.PENDING: self.manager.toggle_pending(self.highlighted_task_index)
            case Execution.ACTIVE: self.manager.toggle_active(self.highlighted_task_index)

if __name__ == "__main__":
    # Standard curses wrapper handles terminal initialisation and cleanup
    error_msgs = wrapper(main)
    if error_msgs is not None:
        for index in range(len(error_msgs)): print(error_msgs[index])