import curses
import json
from curses import wrapper
from curses.textpad import rectangle

#decorator that enables saving behaviour on a function. Base function must pass the list of dictionaries to be saved as its first arguement
def sorts_saves_tasks(base_fn):
    def enhanced_fn(*args, **kwargs):
        #expected return; as in xG = Expected Goals
        xReturn = base_fn(*args, **kwargs)
        list_dicts = args[0]
        #sorts the list with active and pending tasks taking priority respectfully
        list_dicts.sort(key = lambda Dict: (not Dict["active"], not Dict["pending"]))
        #saves to file
        with open ("tasks.json", "w") as f:
            json.dump(list_dicts, f)
        return xReturn
    return enhanced_fn

class invalid_index(Exception):
    pass

def main(stdscr):
    MAX_ACTIVE = 3
    #initialises text colour and permanently turns on green text attribute
    curses.init_pair(1, curses.COLOR_GREEN, curses.COLOR_BLACK)
    GREEN_TEXT = curses.color_pair(1)
    stdscr.attron(GREEN_TEXT)

    list_dicts, current_active = init_list_dicts(MAX_ACTIVE)
    while True:
        y, x = display_tasks(list_dicts, stdscr)
        #stops the rectangles from rendering badly if tasks is empty
        if list_dicts != []:
            render_ui(stdscr, y, x, current_active, MAX_ACTIVE)
        #informs the user that no tasks exist at the moment
        else:
            empty_prompt = "(No tasks exist)"
            stdscr.addstr(2, 6, empty_prompt)
            render_ui(stdscr, 3, len(empty_prompt) + 5, current_active, MAX_ACTIVE)
        execution, int_index, mod_task = interaction_logic(list_dicts, stdscr, y, current_active, MAX_ACTIVE)
        match execution:
            case "none":
                break
            case "a" | "e" | "d" | "f" | "p":
                current_active = modify_tasks(list_dicts, execution, int_index, mod_task, current_active)
            case _:
                continue      
        
    #Turns off text colour attribute
    stdscr.attroff(GREEN_TEXT)

def init_list_dicts(MAX_ACTIVE):
    try:
        with open("tasks.json", "r") as f:
            list_dicts = json.load(f)
            current_active = enforce_max_active(list_dicts, MAX_ACTIVE)
            return list_dicts, current_active

    except (FileNotFoundError, json.JSONDecodeError):
        return [], 0
#fucntion that enforces that only a max of 3 tasks are active at once
@sorts_saves_tasks
def enforce_max_active(list_dicts, MAX_ACTIVE):
    current_active = 0
    for Dict in list_dicts:
        if Dict["active"] and Dict["pending"]: 
            current_active += 1
        if (current_active > MAX_ACTIVE and Dict["active"]) or (Dict["active"] and not Dict["pending"]):
            Dict["active"] = not Dict["active"]
    return current_active

def display_tasks(lisst_dicts, stdscr):
    stdscr.clear()
    y = 2
    x = 0
    stdscr.addstr(1, 6, "tasks:")
    for index, Dict in enumerate(lisst_dicts, start=1):
        task_line = f"{index}. {Dict["task"]}"
        if Dict["active"]:
            stdscr.addstr(y, 2, "*")
        if not Dict["pending"]:
            stdscr.addstr(y, 6, task_line, curses.A_DIM) 
        else:
            stdscr.addstr(y, 6, task_line)
        y += 1
        x = max(x, len(task_line))

    return y, x + 6

def render_ui(stdscr, y ,x, current_active, MAX_ACTIVE):
    if 0 < current_active <= MAX_ACTIVE:
        rectangle(stdscr, 1, 0, current_active + 2 ,4)

    rectangle(stdscr, 0, 5, y, x)

def position_prompt(stdscr, y):
    position_prompt = "Which position would you like to modify: "
    stdscr.addstr(y + 2, 6, position_prompt); stdscr.clrtobot()
    stdscr.addstr(y + 3, 6, "Enter 'none' or '0' to exit.")
    stdscr.addstr(y + 4, 6, "Enter position at the brim or '+' to add a new task at the end")
    stdscr.addstr(y + 5, 2, "*   Active tasks are currently being accomplished. Maximum: 3")
    stdscr.addstr(y + 6, 6, "Grey tasks have been marked as finished", curses.A_DIM)
    stdscr.move(y + 2, len(position_prompt) + 6)
    #let's user input get echoed on the screen whilst typing
    curses.echo()
    human_index = stdscr.getstr().decode("utf-8").strip().lower()
    curses.noecho()
    return human_index

def execution_prompt(list_dicts, stdscr, y, current_active, MAX_ACTIVE, int_human_index):
    stdscr.addstr(y + 2, 6, f"Position: {int_human_index}"); stdscr.clrtobot()
    stdscr.addstr(y + 3, 6, "Press 'a' to add a task, 'e' to edit tasks, 'd' to delete tasks and 'q' to unselect position.")
    stdscr.addstr(y + 4, 6, "Push 'p' to toggle a task as active")
    stdscr.addstr(y + 5, 6, "Press 'f' to toggle a task as finished")
    stdscr.addstr(y + 7, 6, f"Active tasks: {current_active}/{MAX_ACTIVE}")
    if not list_dicts[int_human_index - 1]["pending"]:
        stdscr.addstr(y + 8, 6, f"Finished tasks cannot be set to active", curses.A_DIM)
    #Hides the cursor
    curses.curs_set(0)
    execution = stdscr.getkey().lower()
    curses.curs_set(1)
    return execution

def interaction_logic(list_dicts, stdscr, y, current_active, MAX_ACTIVE,):
    #the functional code of this are small enough to warramt a single function
    #most of the length is just boilerplate for error handling
    human_index = position_prompt(stdscr, y)
    #triggers app closing
    if human_index in ("none", "0"):
        return "none", None, None
    try:
        #makes it so that inputing a + auto leads to adding a task at the brim
        if human_index == "+":
            int_human_index = len(list_dicts) + 1
        else:
            #throws ValueError often
            int_human_index = int(human_index)
        #plus one to account for when a use wants to add at the brim of the tasks
        if 0 < int_human_index <= len(list_dicts) + 1:
            #this loop exists to stop falling back to main menu when the user doesn't enter a valid option at getkey()
            #that was bad for UX
            while True:
                #makes it such that entering the positon at the brim auto leads to add execution
                if int_human_index != len(list_dicts) + 1:
                    #should erase only what will be overwritten. solution => clrtobot: clears everything to the right and below the cursor
                    execution = execution_prompt(list_dicts, stdscr, y, current_active, MAX_ACTIVE, int_human_index)
                else:
                    execution = "a"
                #I like this form of inputing processing for now because it is explicit
                #Also I don't really trust python to not store the variables on the heap. This feels more memory safe.
                match execution:
                    case "q":
                        return None, None, None
                    case "d":
                        return execution, int_human_index - 1, None
                    case "f":
                        return execution, int_human_index - 1, None
                    case "p":
                        #prevents the creation of active task if at max or the task in marked as finished by holding the frame
                        if (current_active == MAX_ACTIVE and not list_dicts[int_human_index - 1]["active"]) or not list_dicts[int_human_index - 1]["pending"]:
                            continue
                        #defensive programming in case of vodo
                        elif current_active > MAX_ACTIVE:
                            current_active = enforce_max_active(list_dicts,MAX_ACTIVE)
                            return None, None, None
                        else:
                            return execution, int_human_index - 1, None
                    case "a" | "e":
                        if execution == "a":
                            choosen_execution = "task"
                        else:
                            choosen_execution = "edit"
                        stdscr.addstr(y + 2, 6, f"Position: {int_human_index}"); stdscr.clrtobot()
                        stdscr.addstr(y + 3, 6, f"new {choosen_execution}: ")
                        curses.echo()
                        mod_task = stdscr.getstr().decode("utf-8").strip()
                        curses.noecho()
                        return execution, int_human_index - 1, mod_task
                #entering an invallid option at getkey holds the frame with this 'continue'
                    case _:
                        continue
        #throws invalid_index if position index inputs is out of logical scope of the tasks
        else:
            raise invalid_index
    #for UX reasons, I've decided these two exceptions should just trigger the a refresh of the frame
    except invalid_index:
        return None, None, None
    except ValueError:
        return None, None, None

@sorts_saves_tasks
def modify_tasks(list_dicts, execution, int_index, mod_task, current_active): 
    match execution:
        case "a":
            Dict = {
                "task": mod_task,
                "active": False,
                "pending": True
            }
            list_dicts.insert(int_index, Dict)
        case "e":
            list_dicts[int_index]["task"] = mod_task
        case "d":
            list_dicts.pop(int_index)
        case "f":
            if list_dicts[int_index]["active"]:
                list_dicts[int_index]["active"] = not list_dicts[int_index]["active"]
                current_active -= 1
            list_dicts[int_index]["pending"] = not list_dicts[int_index]["pending"]
        case "p":
            list_dicts[int_index]["active"] = not list_dicts[int_index]["active"]
            if not list_dicts[int_index]["active"]:
                current_active -= 1
            else:
                current_active += 1
    return current_active

if __name__ == "__main__":
    #initialises curses and calls main
    wrapper(main)