import sys
import curses
import json
from curses import BUTTON1_DOUBLE_CLICKED, BUTTON1_TRIPLE_CLICKED, REPORT_MOUSE_POSITION, wrapper
from curses.textpad import rectangle
from enum import Enum, auto

def sorts_saves_tasks(base_method):
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
        #cleans up any external json file manipulation
        current_active, current_pending, changes = 0, 0, False
        for Dict in self.list_dicts:
            if Dict["pending"]: current_pending += 1
            if (Dict["active"] and not Dict["pending"]):
                Dict["active"] = False
                if not changes: changes = True
            # Deactivate if over limit or if task was finished while active
            if current_active == self.MAX_ACTIVE and Dict["active"]:
                Dict["active"] = False
                if not changes: changes = True
            if Dict["active"] and Dict["pending"]: current_active += 1
        self.list_dicts.sort(key=lambda Dict: (not Dict["active"], not Dict["pending"]))
        if changes:
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
        if not (not self.list_dicts[index]["active"] and self.current_active >= self.MAX_ACTIVE): 
            self.list_dicts[index]["active"] = not self.list_dicts[index]["active"]
            self.current_active += 1 if self.list_dicts[index]["active"] else -1

    def get_tasks(self): return self.list_dicts
    def get_count(self): return len(self.list_dicts)
    def get_task_at(self, index): return self.list_dicts[index]

class execution_enum(Enum):
    ADD = auto()
    EDIT = auto()
    DELETE = auto()
    PENDING = auto()
    ACTIVE = auto()
    QUIT = auto()
    EXIT_APP = auto()

class input_state_enum(Enum):
    POSITION = auto()
    EXECUTE = auto()
    STRING = auto()

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

    try:
        app = tasks_app(stdscr, MAX_ACTIVE=3)
        app.run()
    finally:
        app._set_mouse_tracking(False)
    
    return None

class tasks_app:
    def __init__(self, stdscr, MAX_ACTIVE=3):
        self.stdscr = stdscr
        self.manager = TaskManager(max_active=MAX_ACTIVE)
        self.terminal_height, self.terminal_width = self.stdscr.getmaxyx()

        # Layout Geometry
        self.ACTIVE_MARK_X, self.HEADER_Y, self.PAD_START_Y, self.INFO_PROMPTS_HEIGHT = 1, 0, 2, 7
        self.INDEX_START_X = self.ACTIVE_MARK_X + 3

        self.header_x = self.header_x = 6 + len(str(self.manager.get_count()))
        self.rework_windows = False
        self.highlighted_task_index = None
        self.scroll_offset, self.situational_task, self.situational_shift, self.max_scroll_offset, self.number_of_displayed_tasks = 0, 0, 0, 0, 0
        


        self.INFO_PROMPTS_START_Y = min(self.manager.get_count() + self.PAD_START_Y + 2, self.terminal_height - self.INFO_PROMPTS_HEIGHT)
        
        self.tasks_ui_window = curses.newwin(self.terminal_height, 
                                             self.terminal_width, 0, 0)
        self.pad_height, self.pad_width = 1000, 1000
        self.tasks_pad = curses.newpad(self.pad_height, self.pad_width)

        #3 tasks lines + 1 for rectangle + 1 for gap = 5
        self.APP_MINIMUM_HEIGHT = self.PAD_START_Y + self.INFO_PROMPTS_HEIGHT + 5
        #calculated before hand. Value subject to change as app develops
        self.APP_MINIMUM_WIDTH = 55

        self.input_state = input_state_enum.POSITION

        self.tasks_ui_window.keypad(True)
        curses.mousemask(curses.ALL_MOUSE_EVENTS | REPORT_MOUSE_POSITION) 
        curses.cbreak()
        curses.init_pair(1, curses.COLOR_GREEN, 234)
        curses.init_pair(2, curses.COLOR_GREEN, 235)
        curses.init_pair(3, curses.COLOR_WHITE, 234)
        curses.init_pair(4, curses.COLOR_WHITE, 235)
        self.GREEN_TEXT = curses.color_pair(1)
        self.GREEN_TEXT_ALT = curses.color_pair(2)
        self.FINISHED_TEXT = curses.color_pair(3) | curses.A_DIM
        self.FINISHED_TEXT_ALT = curses.color_pair(4) | curses.A_DIM

        self.pad_end_Y = min(self.manager.get_count() + self.PAD_START_Y - 1 + self.situational_task,
                            self.terminal_height - self.INFO_PROMPTS_HEIGHT - 3 + self.situational_task)
        self.executions_text = ["ADD", "EDIT", "TOGGLE ACTIVE", "TOGGLE FINISHED", "DELETE", "CANCEL"]
        
        self.tasks_ui_window.attron(self.GREEN_TEXT)

    def run(self):
        while True:
            if self.input_state != input_state_enum.POSITION: self.input_state = input_state_enum.POSITION
            self.render_frame()
            execution, mod_task = self.process_interaction()
            if execution == execution_enum.EXIT_APP: break
            if execution: self.process_execution(execution, mod_task)

    #uses escape sequences to enable or disable all mouse tracking modes
    #tracking persisting after crashes lead to consistent crashing on that terminal intance from then on
    def _set_mouse_tracking(self, should_enable):
        esc_seq_end = "h" if should_enable else "l"
        sys.stdout.write(
                f"\033[?1000{esc_seq_end}"
                f"\033[?1000{esc_seq_end}"
                f"\033[?1000{esc_seq_end}"               
                f"\033[?1000{esc_seq_end}"
                )
        sys.stdout.flush()

    def printstr(self, window, string, y = None, x = None, style = None):
        window_height, window_width = window.getmaxyx()
        display_string = string
        # Boundary check to prevent crashes on small terminal heights
        if y is not None and (y < 0 or y >= window_height): return

        if window is self.tasks_pad:
            available_space = self.terminal_width - len(str(self.manager.get_count())) - self.INDEX_START_X - 3
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

        if string_view_start + available_space < len(string): window.addch(">", curses.A_REVERSE)

    def render_frame(self, execution = None):
        self.screen_size_warning_frame()
        
        number_of_tasks = self.manager.get_count()
        self.header_x = 6 + len(str(number_of_tasks))

        self.tasks_ui_window.erase()
        self.tasks_pad.erase()

        if number_of_tasks > 0:
            list_dicts = self.manager.get_tasks()
            #a task that only appears when user to one place over the final task
            self.situational_task = 1 if self.highlighted_task_index == number_of_tasks else 0
            self.pad_end_Y = min(number_of_tasks + self.PAD_START_Y - 1 + self.situational_task,
                            self.terminal_height - self.INFO_PROMPTS_HEIGHT - 3 + self.situational_task)
            
            self.number_of_displayed_tasks = self.pad_end_Y - self.PAD_START_Y
            should_scroll_down = self.highlighted_task_index is not None and self.highlighted_task_index > self.scroll_offset + self.number_of_displayed_tasks
            should_scroll_up = self.highlighted_task_index is not None and self.highlighted_task_index < self.scroll_offset
            if should_scroll_down and self.highlighted_task_index is not None: self.scroll_offset = self.highlighted_task_index - self.number_of_displayed_tasks
            if should_scroll_up and self.highlighted_task_index is not None: self.scroll_offset = self.highlighted_task_index
            #sometimes, situational task has a displayed index that is one digit longer than the others
            self.situational_shift = 1 if len(str(number_of_tasks + self.situational_task)) > len(str(number_of_tasks)) else 0
            
            self.render_ui_elements(number_of_tasks)
            if number_of_tasks + self.situational_task > self.pad_height:
                self.pad_height = number_of_tasks + self.situational_task
                self.tasks_pad.resize(self.pad_height, self.pad_width)
            self.printstr(self.tasks_ui_window, "tasks:", self.HEADER_Y, self.header_x + self.situational_shift, self.GREEN_TEXT | curses.A_BOLD)
            for index, Dict in enumerate(list_dicts):
                if Dict["active"] and index >= self.scroll_offset:
                    self.printstr(self.tasks_ui_window, "*", index + self.PAD_START_Y - self.scroll_offset, self.ACTIVE_MARK_X)
                style = ((self.GREEN_TEXT if index % 2 == 0 else self.GREEN_TEXT_ALT) if Dict["pending"] else 
                        (self.FINISHED_TEXT if index % 2 == 0 else self.FINISHED_TEXT_ALT))
                if index == self.highlighted_task_index: style = style | curses.A_REVERSE
                index_margin = (" " * ((len(str(number_of_tasks)) - len(str(index + 1))) + self.situational_shift) 
                                if len(str(index + 1)) < len(str(number_of_tasks)) + self.situational_shift else "")
                if len(f"{index_margin}{index + 1}{Dict['task']}") > self.pad_width:
                    self.pad_width = len(Dict["task"])
                    self.tasks_pad.resize(self.pad_height, self.pad_width)
                self.printstr(self.tasks_pad, f"{index_margin}{index + 1}{Dict['task']}", index, 0, style,)

            if self.highlighted_task_index == number_of_tasks:
                style = self.GREEN_TEXT | curses.A_REVERSE if self.highlighted_task_index % 2 == 0 else self.GREEN_TEXT_ALT | curses.A_REVERSE
                self.printstr(self.tasks_pad, f"{number_of_tasks + 1}", number_of_tasks , 0, style)
                if number_of_tasks > self.number_of_displayed_tasks: self.printstr(self.tasks_ui_window, "█", self.pad_end_Y, self.terminal_width - 2)

            self.tasks_ui_window.noutrefresh()
            # pad rendering of indices
            self.tasks_pad.noutrefresh(self.scroll_offset, 0, self.PAD_START_Y, self.INDEX_START_X,
                                       self.pad_end_Y, self.INDEX_START_X + len(str(number_of_tasks)) - 1 + self.situational_shift)
            # pad rendering of task lines
            self.tasks_pad.noutrefresh(self.scroll_offset, len(str(number_of_tasks)) + self.situational_shift, self.PAD_START_Y, self.header_x + self.situational_shift,
                                       self.pad_end_Y, self.terminal_width - 4)
        else:
            self.INFO_PROMPTS_START_Y = self.PAD_START_Y + 2
            self.tasks_ui_window.resize(self.terminal_height, self.terminal_width)

            self.printstr(self.tasks_ui_window, "tasks:", self.HEADER_Y, self.header_x, self.GREEN_TEXT | curses.A_BOLD)
            style = self.GREEN_TEXT | curses.A_REVERSE if self.highlighted_task_index == 0 else self.GREEN_TEXT
            self.printstr(self.tasks_ui_window, "(No tasks exist)", self.PAD_START_Y, self.header_x, style)
            self.tasks_ui_window.noutrefresh()
        match self.input_state:
            case input_state_enum.POSITION: self.position_prompt()
            case input_state_enum.EXECUTE: self.execution_prompt()
            case input_state_enum.STRING: self.task_string_prompt(execution)

        curses.doupdate()

    def render_ui_elements(self, number_of_tasks):
        # Handles Dynamic Window Scaling and UI container rectangles
        if self.rework_windows:
            self.INFO_PROMPTS_START_Y = min(number_of_tasks + self.PAD_START_Y + 2, self.terminal_height - self.INFO_PROMPTS_HEIGHT)
            self.tasks_ui_window.resize(self.terminal_height, self.terminal_width)
            self.rework_windows = False
        # Draw Focus box for active items and Main Container for the list
        if 0 < self.manager.current_active <= self.manager.MAX_ACTIVE:
            active_rectangle_end_y = max(self.manager.current_active + self.PAD_START_Y - self.scroll_offset - 1, self.PAD_START_Y - 1)
            if not active_rectangle_end_y == self.PAD_START_Y - 1:
                rectangle(self.tasks_ui_window, self.PAD_START_Y - 1, self.ACTIVE_MARK_X - 1,
                          max(self.manager.current_active + self.PAD_START_Y - self.scroll_offset, self.PAD_START_Y - 1), self.ACTIVE_MARK_X + 1)
        rectangle(self.tasks_ui_window, self.PAD_START_Y - 1, self.INDEX_START_X - 1,
                self.pad_end_Y + 1, self.INDEX_START_X + len(str(number_of_tasks)) + self.situational_shift)
        rectangle(self.tasks_ui_window, self.PAD_START_Y - 1, self.header_x - 1 + self.situational_shift,
                self.pad_end_Y + 1, self.terminal_width - 3)
        
        scrollbar_height = (min(number_of_tasks + self.PAD_START_Y - 1, self.terminal_height - self.INFO_PROMPTS_HEIGHT - 3) + 1) - self.PAD_START_Y 
        #the ultimate task that can be scrolled to based on how big the viewport is
        #the actual distance the list can travel before it hits the "floor"
        self.max_scroll_offset = number_of_tasks - scrollbar_height
        if self.max_scroll_offset > 0:
            #between 0.0 (The Top) and 1.0 (The Bottom)
            #divide self.max_scroll_offset instead of number_of_tasks so ratio is 1.0 at end of scroll
            scroll_ratio = self.scroll_offset / self.max_scroll_offset   
            scroll_thumb_size = max(int((scrollbar_height / number_of_tasks) * scrollbar_height), 1)
            #without substracting thumb size you'd have the bottom location of it rather than the top
            scroll_thumb_pos = int(scroll_ratio * (scrollbar_height - scroll_thumb_size))
            for i in range(scrollbar_height):
                y = self.PAD_START_Y + i
                x = self.terminal_width - 2
                char = "█" if scroll_thumb_pos <= i < scroll_thumb_pos + scroll_thumb_size else "░"
                self.printstr(self.tasks_ui_window, char, y, x)
        
        self.tasks_ui_window.noutrefresh()

    def screen_size_warning_frame(self):
        cursor_hidden = False
        while self.terminal_height < self.APP_MINIMUM_HEIGHT or self.terminal_width < self.APP_MINIMUM_WIDTH:
            if not cursor_hidden: curses.curs_set(0); cursor_hidden = True
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
        if cursor_hidden: curses.curs_set(1); cursor_hidden = False
    
    def resize_updates(self, execution = None):
        self.terminal_height, self.terminal_width = self.stdscr.getmaxyx()
        if self.highlighted_task_index is not None:
            self.number_of_displayed_tasks = min(self.manager.get_count() + self.PAD_START_Y - 1 + self.situational_task,
                                        self.terminal_height - self.INFO_PROMPTS_HEIGHT - 3 + self.situational_task) - self.PAD_START_Y
            self.scroll_offset = max(self.highlighted_task_index - self.number_of_displayed_tasks, 0)
        self.render_frame(execution)

    def position_prompt(self):
        if self.input_state != input_state_enum.POSITION: self.input_state = input_state_enum.POSITION
        self.printstr(self.tasks_ui_window, "Select a position to modify", self.INFO_PROMPTS_START_Y, self.INDEX_START_X); self.tasks_ui_window.clrtobot()
        self.printstr(self.tasks_ui_window, f"Hit 'Esc', 'q' or '0' to exit.", self.INFO_PROMPTS_START_Y + 1, self.INDEX_START_X)
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
        if self.input_state != input_state_enum.EXECUTE: self.input_state = input_state_enum.EXECUTE
        self.printstr(self.tasks_ui_window, f"Position: {self.highlighted_task_index + 1}", self.INFO_PROMPTS_START_Y, self.INDEX_START_X); self.tasks_ui_window.clrtobot()

        for index, execution in enumerate(self.executions_text, start = 1):
            style = self.GREEN_TEXT | curses.A_REVERSE if highlighted_execution == index else self.GREEN_TEXT
            if index == 3:
                target_task = self.manager.get_task_at(self.highlighted_task_index)
                # greys out "toggle active" when necessary
                if (self.manager.current_active == self.manager.MAX_ACTIVE and not target_task["active"]) or not target_task["pending"]:
                    style = self.FINISHED_TEXT | curses.A_REVERSE if highlighted_execution == index else self.FINISHED_TEXT 
            self.printstr(self.tasks_ui_window, execution, self.INFO_PROMPTS_START_Y + index, self.INDEX_START_X, style)

        self.tasks_ui_window.refresh()

    def task_string_prompt(self, execution):
        if self.input_state != input_state_enum.STRING: self.input_state = input_state_enum.STRING
        choosen_execution = "task" if execution == execution_enum.ADD else "edit"
        self.printstr(self.tasks_ui_window, f"Position: {self.highlighted_task_index + 1}", self.INFO_PROMPTS_START_Y, self.INDEX_START_X); self.tasks_ui_window.clrtobot()
        self.printstr(self.tasks_ui_window, f"{choosen_execution}:", self.INFO_PROMPTS_START_Y + 1, self.INDEX_START_X)
        self.tasks_ui_window.refresh()

    def tasks_navigation(self, window):
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
                    self.resize_updates()
                    curses.curs_set(0) #screen size warning frame can unhide the cursor
                case curses.KEY_MOUSE:
                    _, mouse_x, mouse_y, _, button_state = curses.getmouse()
                    if button_state & (curses.BUTTON1_CLICKED | curses.BUTTON1_DOUBLE_CLICKED | curses.BUTTON1_TRIPLE_CLICKED):
                        within_pad_width = self.header_x + self.situational_shift <= mouse_x <= self.terminal_width - 4
                        within_pad_height = self.PAD_START_Y <= mouse_y <= self.pad_end_Y + self.situational_task
                        if within_pad_width and within_pad_height:
                            self.highlighted_task_index = (mouse_y - self.PAD_START_Y) + self.scroll_offset
                            self.render_frame()
                            break
                    elif button_state & curses.BUTTON4_PRESSED:
                        if self.highlighted_task_index == self.scroll_offset + self.number_of_displayed_tasks and self.scroll_offset != 0:
                            self.highlighted_task_index -= 1
                        if self.scroll_offset != 0: self.scroll_offset -= 1
                    elif button_state & getattr(curses, "BUTTON5_PRESSED", 0x200000):
                        if self.highlighted_task_index == self.scroll_offset and self.scroll_offset != self.max_scroll_offset: self.highlighted_task_index += 1
                        if self.scroll_offset != self.max_scroll_offset: self.scroll_offset += 1
                case curses.KEY_UP:
                    if self.highlighted_task_index is None or self.highlighted_task_index == 0: self.highlighted_task_index = self.manager.get_count()
                    else: self.highlighted_task_index -= 1
                case curses.KEY_DOWN:
                    if self.highlighted_task_index is None or self.highlighted_task_index == self.manager.get_count(): self.highlighted_task_index = 0
                    else: self.highlighted_task_index += 1
                case _: continue
            self.render_frame()
        curses.curs_set(1)
    
    def get_execution(self, window):
        curses.curs_set(0)
        highlighted_execution = None
        number_of_executiions = 6
        while True:
            char_code = window.getch()
            match char_code:
                case code if code == ord("q") or code == ord("Q") or code == ord("0") or code == 27:
                    curses.curs_set(1); return execution_enum.QUIT
                case 10 | 13: #enter key
                    if highlighted_execution is not None:
                        if highlighted_execution == 3:
                            target_task = self.manager.get_task_at(self.highlighted_task_index)
                            # Constraint: Prevent activation if finished or focus slots are full
                            if (self.manager.current_active == self.manager.MAX_ACTIVE and not target_task["active"]) or not target_task["pending"]:
                                continue
                        break
                case curses.KEY_RESIZE: 
                    self.rework_windows = True; self.resize_updates()
                    curses.curs_set(0) #screen size warning frame can unhide the cursor
                case curses.KEY_MOUSE:
                    _, mouse_x, mouse_y, _, button_state = curses.getmouse()
                    if button_state & (curses.BUTTON1_CLICKED | curses.BUTTON1_DOUBLE_CLICKED | curses.BUTTON1_TRIPLE_CLICKED):
                        within_execution_height = self.INFO_PROMPTS_START_Y + 1 <= mouse_y <= self.INFO_PROMPTS_START_Y + number_of_executiions
                        if  within_execution_height:
                            executions_text_index = mouse_y - (self.INFO_PROMPTS_START_Y + 1)
                            within_execution_width = self.INDEX_START_X <= mouse_x <= self.INDEX_START_X + len(self.executions_text[executions_text_index])
                            if within_execution_width:
                                highlighted_execution = executions_text_index + 1
                                if highlighted_execution == 3:
                                    target_task = self.manager.get_task_at(self.highlighted_task_index)
                                    # Constraint: Prevent activation if finished or focus slots are full
                                    if (self.manager.current_active == self.manager.MAX_ACTIVE and not target_task["active"]) or not target_task["pending"]:
                                        self.execution_prompt(highlighted_execution)
                                        continue
                                break 
                case curses.KEY_UP:
                    if highlighted_execution is None or not highlighted_execution > 1: highlighted_execution = number_of_executiions
                    else: highlighted_execution -= 1
                case curses.KEY_DOWN:
                    if highlighted_execution is None or not highlighted_execution < number_of_executiions: highlighted_execution = 1
                    else: highlighted_execution += 1
                case _: continue
            self.execution_prompt(highlighted_execution)
        curses.curs_set(1)
        match highlighted_execution:
            case 1: return execution_enum.ADD
            case 2: return execution_enum.EDIT
            case 3: return execution_enum.ACTIVE
            case 4: return execution_enum.PENDING
            case 5: return execution_enum.DELETE
            case 6: return execution_enum.QUIT

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
                case 27: return None
                case 10 | 13: #Enter key
                    if buffer.strip() != "": return buffer.strip()
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
    
    def process_interaction(self):
        if self.input_state != input_state_enum.POSITION: self.position_prompt()
        self.tasks_navigation(self.tasks_ui_window)
        if self.highlighted_task_index == -1: return execution_enum.EXIT_APP, None
        
        while True:
            # Auto-routing: Brim selection defaults to Add; existing index prompts for action
            if self.highlighted_task_index == self.manager.get_count():
                self.highlighted_task_index = self.manager.current_pending
                self.render_frame()
                execution = execution_enum.ADD
            else: 
                self.execution_prompt()
                execution = self.get_execution(self.tasks_ui_window)
            
            match execution:
                case execution_enum.QUIT: return None, None
                case execution_enum.DELETE | execution_enum.PENDING: return execution, None
                case execution_enum.ACTIVE:
                    return execution, None
                case execution_enum.ADD | execution_enum.EDIT:
                    task_string = ""
                    if execution == execution_enum.EDIT: task_string = self.manager.get_task_at(self.highlighted_task_index)["task"]
                    self.task_string_prompt(execution)
                    style = self.FINISHED_TEXT if execution == execution_enum.EDIT and not self.manager.get_task_at(self.highlighted_task_index)["pending"] else None
                    task_string = self.get_string(self.tasks_ui_window, execution, task_string, style)
                    if task_string is None: 
                        if self.highlighted_task_index == self.manager.get_count(): return None, None
                        else: continue
                    else: return execution, task_string
                case _: continue

    def process_execution(self, execution, mod_task = None):
        # Bridges UI intent to Model logic and updates layout dimensions if needed
        match execution:
            case execution_enum.ADD:
                self.manager.add_task(self.highlighted_task_index, mod_task)
                self.rework_windows = True
            case execution_enum.EDIT:
                self.manager.edit_task(self.highlighted_task_index, mod_task)
            case execution_enum.DELETE:
                if self.highlighted_task_index + 1 == self.manager.get_count(): self.scroll_offset -= 1
                self.manager.delete_task(self.highlighted_task_index)
                self.rework_windows = True
            case execution_enum.PENDING: self.manager.toggle_pending(self.highlighted_task_index)
            case execution_enum.ACTIVE: self.manager.toggle_active(self.highlighted_task_index)

if __name__ == "__main__":
    # Standard curses wrapper handles terminal initialisation and cleanup
    error_msgs = wrapper(main)
    if error_msgs is not None:
        for index in range(len(error_msgs)): print(error_msgs[index])
