import curses
import json
from curses import wrapper
from curses.textpad import rectangle

#decorator that enables saving behaviour on a method of a class that contains the list of dictionaries
def sorts_saves_tasks(base_method):
    def enhanced_fn(self, *args, **kwargs):
        #expected return; as in xG = Expected Goals
        xReturn = base_method(self, *args, **kwargs)
        #sorts the list with active and pending tasks taking priority respectfully
        self.list_dicts.sort(key = lambda Dict: (not Dict["active"], not Dict["pending"]))
        #saves to file
        with open ("tasks.json", "w") as f:
            json.dump(self.list_dicts, f)
        return xReturn
    return enhanced_fn

class invalid_index(Exception):
    pass

def main(stdscr):
    #initialises text colour and permanently turns on green text attribute
    curses.init_pair(1, curses.COLOR_GREEN, curses.COLOR_BLACK)
    GREEN_TEXT = curses.color_pair(1)
    stdscr.attron(GREEN_TEXT)

    #Instantiate and run the app
    app = tasks_app(stdscr, GREEN_TEXT, MAX_ACTIVE=3)
    app.run()

    #Turns off text colour attribute
    stdscr.attroff(GREEN_TEXT)

class tasks_app:
    def __init__(self, stdscr, GREEN_TEXT, MAX_ACTIVE=3):
        self.stdscr = stdscr
        self.GREEN_TEXT = GREEN_TEXT
        self.MAX_ACTIVE = MAX_ACTIVE
        # Get terminal size for safety
        self.terminal_height, self.terminal_width = self.stdscr.getmaxyx()
        
        # Execution Constants
        self.ADD_EXECUTE = "a"
        self.EDIT_EXECUTE = "e"
        self.DELETE_EXECUTE = "d"
        self.PENDING_EXECUTE = "f"
        self.ACTIVE_EXECUTE = "p"
        self.QUIT_EXECUTE = "q"
        self.EXIT_APP = "none"

        # Layout Constants
        self.LEFT_MARGIN = 4
        self.ACTIVE_MARK_X = 1
        self.HEADER_Y = 0
        self.PAD_START_Y = 2
        self.EMPTY_PROMPT = "(No tasks exist)"

        # Application State
        self.current_active = 0
        self.number_of_tasks = self.load_tasks()
        # + 2 repesents ". " 
        self.length_of_tasks = max((len(Dict['task']) + len(str(index)) + 2 for index, Dict in enumerate(self.list_dicts, start = 1)),
                                   default = 0)
        self.rework_windows = False
        self.recheck_length_of_tasks = False

        self.task_ui_elements_window = curses.newwin(self.number_of_tasks + self.PAD_START_Y + 2, self.length_of_tasks + self.LEFT_MARGIN + 2, 0, 0)
        self.task_ui_elements_window.attron(GREEN_TEXT)

        #pad for tasks
        pad_height = max(1000, len(self.list_dicts) * 2)
        PAD_WIDTH = 1000
        self.tasks_pad = curses.newpad(pad_height, PAD_WIDTH)

        input_window_height = 7
        self.input_window = curses.newwin(input_window_height, self.terminal_width, 
                                          self.number_of_tasks + self.PAD_START_Y + 2, 0)
        self.input_window.attron(GREEN_TEXT)

    def run(self):
        while True:
            self.render_tasks()
            
            execution, int_index, mod_task = self.process_interaction()

            match execution:
                case self.EXIT_APP:
                    break
                case self.ADD_EXECUTE | self.EDIT_EXECUTE | self.DELETE_EXECUTE | self.PENDING_EXECUTE | self.ACTIVE_EXECUTE:
                    self.process_execution(execution, int_index, mod_task)
                case _:
                    continue

    def load_tasks(self):
        try:
            with open("tasks.json", "r") as f:
                self.list_dicts = json.load(f)
                self.enforce_max_active()
        except (FileNotFoundError, json.JSONDecodeError):
            self.list_dicts = []
        finally:
            return len(self.list_dicts)

    #method that enforces that only a max of 3 tasks are active at once
    @sorts_saves_tasks
    def enforce_max_active(self):
        self.current_active = 0
        for Dict in self.list_dicts:
            if Dict["active"] and Dict["pending"]: 
                self.current_active += 1
            if (self.current_active > self.MAX_ACTIVE and Dict["active"]) or (Dict["active"] and not Dict["pending"]):
                Dict["active"] = not Dict["active"]
    
    def render_tasks(self):
        #prevents ghosting when the pad refresh area get's smaller
        self.stdscr.erase()
        self.stdscr.noutrefresh()

        # 2. Draw the UI BOX first
        self.render_ui_elements()

        self.tasks_pad.erase()

        pad_y = 0

        if self.list_dicts != []:
            self.task_ui_elements_window.addstr(self.HEADER_Y, self.LEFT_MARGIN, "tasks:", self.GREEN_TEXT | curses.A_BOLD)
            for index, Dict in enumerate(self.list_dicts, start=1):
                if Dict["active"]:
                    self.task_ui_elements_window.addstr(pad_y + self.PAD_START_Y, self.ACTIVE_MARK_X, "*")
                style = self.GREEN_TEXT | curses.A_NORMAL if Dict["pending"] else curses.A_DIM
                self.tasks_pad.addstr(pad_y, 0, f"{index}. {Dict['task']}", style)
                pad_y += 1

            self.task_ui_elements_window.noutrefresh()
            # Refresh pad to screen - these need to be valid screen coordinates
            self.tasks_pad.noutrefresh(
                0, 0,  # Top-left of pad content
                self.PAD_START_Y, self.LEFT_MARGIN,  # Where to start displaying on screen
                #minus one to correct discrepancy between zero based(scr coordinates) and none zero based(number of tasks)
                min(self.number_of_tasks + self.PAD_START_Y - 1, self.terminal_height - 5), min(self.length_of_tasks + self.LEFT_MARGIN - 1, self.terminal_width - 1)# Bottom-right corner
            )
        else:

            self.task_ui_elements_window.addstr(self.HEADER_Y, self.LEFT_MARGIN, "tasks:", self.GREEN_TEXT | curses.A_BOLD)
            self.task_ui_elements_window.addstr(self.PAD_START_Y, self.LEFT_MARGIN, self.EMPTY_PROMPT)
        
            self.task_ui_elements_window.noutrefresh()

        curses.doupdate()

    def render_ui_elements(self):
        self.task_ui_elements_window.erase()

        if self.list_dicts != []:
            if self.rework_windows:
                self.input_window.mvwin(self.number_of_tasks  + self.PAD_START_Y + 2, 0)
                self.task_ui_elements_window.resize(self.number_of_tasks + self.PAD_START_Y + 2, self.length_of_tasks + self.LEFT_MARGIN + 2)
                self.rework_windows = False

            if 0 < self.current_active <= self.MAX_ACTIVE:
                rectangle(self.task_ui_elements_window, 
                        self.PAD_START_Y - 1, self.ACTIVE_MARK_X - 1,
                        self.current_active + self.PAD_START_Y , self.ACTIVE_MARK_X + 1)    
            rectangle(self.task_ui_elements_window,
                    self.PAD_START_Y - 1, self.LEFT_MARGIN - 1,
                    self.PAD_START_Y + self.number_of_tasks, self.length_of_tasks + self.LEFT_MARGIN)
            
        else:
            self.input_window.mvwin(self.PAD_START_Y + 3, 0)
            self.task_ui_elements_window.resize(self.PAD_START_Y + 1, len(self.EMPTY_PROMPT) + self.LEFT_MARGIN + 1)
        
        self.task_ui_elements_window.noutrefresh()


    def position_prompt(self):
        position_prompt = "Which position would you like to modify: "

        self.input_window.addstr(0, self.LEFT_MARGIN, position_prompt); self.input_window.clrtobot()
        self.input_window.addstr(1, self.LEFT_MARGIN, f"Enter '{self.EXIT_APP}' or '0' to exit.")
        self.input_window.addstr(2, self.LEFT_MARGIN, "Enter position at the brim or '+' to add a new task at the end")
        self.input_window.addstr(3, self.LEFT_MARGIN, "Grey tasks have been marked as finished", curses.A_DIM)
        if self.current_active > 0:    
            rectangle(self.input_window,
                      3, self.ACTIVE_MARK_X - 1,
                      5, self.ACTIVE_MARK_X + 1)
            self.input_window.addstr(4, self.ACTIVE_MARK_X, "*")
            self.input_window.addstr(4, self.LEFT_MARGIN, f"Active tasks are currently being accomplished. Maximum: {self.MAX_ACTIVE}")

        self.input_window.move(0, self.LEFT_MARGIN + len(position_prompt))

        self.input_window.refresh()

        #let's user input get echoed on the screen whilst typing
        curses.echo()
        human_index = self.input_window.getstr().decode("utf-8").strip().lower()
        curses.noecho()
        return human_index

    def execution_prompt(self, int_human_index):
        self.input_window.addstr(0, self.LEFT_MARGIN, f"Position: {int_human_index}"); self.input_window.clrtobot()
        self.input_window.addstr(1, self.LEFT_MARGIN, f"Press '{self.ADD_EXECUTE}' to add a task, '{self.EDIT_EXECUTE}' to edit tasks, '{self.DELETE_EXECUTE}' to delete tasks and '{self.QUIT_EXECUTE}' to unselect position.")
        self.input_window.addstr(2, self.LEFT_MARGIN, f"Push '{self.ACTIVE_EXECUTE}' to toggle a task as active")
        self.input_window.addstr(3, self.LEFT_MARGIN, f"Press '{self.PENDING_EXECUTE}' to toggle a task as finished")
        self.input_window.addstr(5, self.LEFT_MARGIN, f"Active tasks: {self.current_active}/{self.MAX_ACTIVE}")

        if not self.list_dicts[int_human_index - 1]["pending"]:
            self.input_window.addstr(6, self.LEFT_MARGIN, f"Finished tasks cannot be set to active", curses.A_DIM)

        self.input_window.refresh()

        #Hides the cursor
        curses.curs_set(0)
        execution = self.input_window.getkey().lower()
        curses.curs_set(1)
        return execution

    def task_string_prompt(self, execution, int_human_index):
        #we don't need echo being triggered each loop cycle
        curses.echo()
        #looped to prevent annoying ux if empty string is provided
        while True:
            choosen_execution = "task" if execution == self.ADD_EXECUTE else "edit"
            self.input_window.addstr(0, self.LEFT_MARGIN, f"Position: {int_human_index}"); self.input_window.clrtobot()
            self.input_window.addstr(1, self.LEFT_MARGIN, f"new {choosen_execution}: ")
            #conditional to catch empty string. 
            # := lets you assign inside conditional expressions and returns false if assigned something empty
            if not (mod_task := self.input_window.getstr().decode("utf-8").strip()):
                continue    
            curses.noecho()
            return mod_task
            

    def process_interaction(self):
        #the functional code of this are small enough to warrant a single method
        #most of the length is just boilerplate for error handling
        human_index = self.position_prompt()
        #triggers app closing
        if human_index in (self.EXIT_APP, "0"):
            return self.EXIT_APP, None, None
        try:
            #makes it so that inputing a '+' auto leads to adding a task at the brim
            if human_index == "+":
                int_human_index = len(self.list_dicts) + 1
            else:
                #throws ValueError often
                int_human_index = int(human_index)
            #plus one to account for when a use wants to add at the brim of the tasks
            if not (0 < int_human_index <= len(self.list_dicts) + 1):
                #throws invalid_index if position index inputs is out of logical scope of the tasks
                raise invalid_index
        #for UX reasons, I've decided these two exceptions should just trigger the a refresh of the frame
        except (invalid_index, ValueError):
            return None, None, None
        #this loop exists to stop falling back to main menu when the user doesn't enter a valid option at getkey()
        #that was bad for UX
        while True:
            #makes it such that entering the positon at the brim auto leads to add execution
            if int_human_index != len(self.list_dicts) + 1:
                #should erase only what will be overwritten. solution => clrtobot: clears everything to the right and below the cursor
                execution = self.execution_prompt(int_human_index)
            else:
                execution = self.ADD_EXECUTE
            #I like this form of inputing processing for now because it is explicit
            match execution:
                case self.QUIT_EXECUTE:
                    return None, None, None
                case self.DELETE_EXECUTE | self.PENDING_EXECUTE:
                    return execution, int_human_index - 1, None
                case self.ACTIVE_EXECUTE:
                    #prevents the creation of active task if at max or the task in marked as finished by holding the frame
                    if (self.current_active == self.MAX_ACTIVE and not self.list_dicts[int_human_index - 1]["active"]) or not self.list_dicts[int_human_index - 1]["pending"]:
                        continue
                    #defensive programming in case of voodoo
                    elif self.current_active > self.MAX_ACTIVE:
                        self.enforce_max_active()
                        return None, None, None
                    else:
                        return execution, int_human_index - 1, None
                #cool implementation for taking a new string for new and edited tasks both using the singlular call
                case self.ADD_EXECUTE | self.EDIT_EXECUTE:
                    mod_task = self.task_string_prompt(execution, int_human_index)
                    return execution, int_human_index - 1, mod_task
                case _:
                    #entering an invallid option at getkey holds the frame with this 'continue'
                    continue

    @sorts_saves_tasks
    def process_execution(self, execution, int_index, mod_task):
        match execution:
            case self.ADD_EXECUTE:
                Dict = {
                    "task": mod_task,
                    "active": False,
                    "pending": True
                }
                self.list_dicts.insert(int_index, Dict)
                self.number_of_tasks += 1
                self.rework_windows = True
                new_task_display_length = len(mod_task) + len(str(int_index + 1)) + 2
                if new_task_display_length > self.length_of_tasks:
                    self.length_of_tasks = new_task_display_length
            case self.EDIT_EXECUTE:
                self.list_dicts[int_index]["task"] = mod_task
                modded_task_display_length = len(mod_task) + len(str(int_index + 1)) + 2
                if modded_task_display_length > self.length_of_tasks:
                    self.length_of_tasks = modded_task_display_length
                    self.rework_windows = True
            case self.DELETE_EXECUTE:
                deleted_task_display_length = len(self.list_dicts[int_index]["task"]) + len(str(int_index + 1)) + 2
                self.list_dicts.pop(int_index)
                self.number_of_tasks -= 1
                self.rework_windows = True
                if deleted_task_display_length == self.length_of_tasks:
                    self.length_of_tasks = max((len(Dict['task']) + len(str(index)) + 2 for index, Dict in enumerate(self.list_dicts, start = 1)),
                                               default = 0)
            case self.PENDING_EXECUTE:
                if self.list_dicts[int_index]["active"]:
                    self.list_dicts[int_index]["active"] = not self.list_dicts[int_index]["active"]
                    self.current_active -= 1
                self.list_dicts[int_index]["pending"] = not self.list_dicts[int_index]["pending"]
            case self.ACTIVE_EXECUTE:
                self.list_dicts[int_index]["active"] = not self.list_dicts[int_index]["active"]
                if not self.list_dicts[int_index]["active"]:
                    self.current_active -= 1
                else:
                    self.current_active += 1

if __name__ == "__main__":
    #initialises curses and calls main
    wrapper(main)