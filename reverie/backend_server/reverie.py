"""
Author: Joon Sung Park (joonspk@stanford.edu)

File: reverie.py
Description: This is the main program for running generative agent simulations
that defines the ReverieServer class. This class maintains and records all  
states related to the simulation. The primary mode of interaction for those  
running the simulation should be through the open_server function, which  
enables the simulator to input command-line prompts for running and saving  
the simulation, among other tasks.

Release note (June 14, 2023) -- Reverie implements the core simulation 
mechanism described in my paper entitled "Generative Agents: Interactive 
Simulacra of Human Behavior." If you are reading through these lines after 
having read the paper, you might notice that I use older terms to describe 
generative agents and their cognitive modules here. Most notably, I use the 
term "personas" to refer to generative agents, "associative memory" to refer 
to the memory stream, and "reverie" to refer to the overarching simulation 
framework.
"""
import json
import numpy
import datetime
import pickle
import time
import math
import os
import shutil
import traceback
import argparse

from selenium import webdriver

from global_methods import *
from utils import *
from maze import *
from persona.persona import *

current_file = os.path.abspath(__file__)

def trace_calls_and_lines(frame, event, arg):
    if event == 'call':
        code = frame.f_code
        filename = code.co_filename
        short_filename = os.path.relpath(filename)
        if os.path.abspath(filename).startswith(os.getcwd()):
        # # if os.path.abspath(filename).startswith():
        # # if filename == current_file:
            print(f"Calling function: {code.co_name} in {short_filename}:{code.co_firstlineno}")

##############################################################################
#                                  REVERIE                                   #
##############################################################################

class ReverieServer: 
  def __init__(self, 
               fork_sim_code,
               sim_code,
               owner = "public",
               ):
    print ("(reverie): Temp storage: ", fs_temp_storage)
        
    # FORKING FROM A PRIOR SIMULATION:
    # <fork_sim_code> indicates the simulation we are forking from. 
    # Interestingly, all simulations must be forked from some initial 
    # simulation, where the first simulation is "hand-crafted".
    self.fork_sim_code = fork_sim_code
    fork_folder = f"{fs_storage}/{self.fork_sim_code}"

    # <sim_code> indicates our current simulation. The first step here is to 
    # copy everything that's in <fork_sim_code>, but edit its 
    # reverie/meta/json's fork variable. 
    self.sim_code = sim_code
    sim_folder = f"{fs_storage}/{self.sim_code}"
    # copyanything(fork_folder, sim_folder) # 模版的使用

    with open(f"{sim_folder}/reverie/meta.json") as json_file:  
      parent = json.load(json_file)["parent"]

    with open(f"{sim_folder}/reverie/meta.json") as json_file:  
      reverie_meta = json.load(json_file)

    with open(f"{sim_folder}/reverie/meta.json", "w") as outfile: 
      reverie_meta["fork_sim_code"] = fork_sim_code
      reverie_meta["owner"] = owner
      reverie_meta["parent"] = parent
      outfile.write(json.dumps(reverie_meta, indent=2))

    # LOADING REVERIE'S GLOBAL VARIABLES
    # The start datetime of the Reverie: 
    # <start_datetime> is the datetime instance for the start datetime of 
    # the Reverie instance. Once it is set, this is not really meant to 
    # change. It takes a string date in the following example form: 
    # "June 25, 2022"
    # e.g., ...strptime(June 25, 2022, "%B %d, %Y")
    self.start_time = datetime.datetime.strptime(
                        f"{reverie_meta['start_date']}, 00:00:00",  
                        "%B %d, %Y, %H:%M:%S")
    # <curr_time> is the datetime instance that indicates the game's current
    # time. This gets incremented by <sec_per_step> amount everytime the world
    # progresses (that is, everytime curr_env_file is recieved). 
    self.curr_time = datetime.datetime.strptime(reverie_meta['curr_time'], 
                                                "%B %d, %Y, %H:%M:%S")
    # <sec_per_step> denotes the number of seconds in game time that each 
    # step moves foward. 
    self.sec_per_step = reverie_meta['sec_per_step']
    
    # <maze> is the main Maze instance. Note that we pass in the maze_name
    # (e.g., "double_studio") to instantiate Maze. 
    # e.g., Maze("double_studio")
    self.maze = Maze(reverie_meta['maze_name'])
    
    # <step> denotes the number of steps that our game has taken. A step here
    # literally translates to the number of moves our personas made in terms
    # of the number of tiles. 
    self.step = reverie_meta['step']

    # SETTING UP PERSONAS IN REVERIE
    # <personas> is a dictionary that takes the persona's full name as its 
    # keys, and the actual persona instance as its values.
    # This dictionary is meant to keep track of all personas who are part of
    # the Reverie instance. 
    # e.g., ["Isabella Rodriguez"] = Persona("Isabella Rodriguezs")
    self.personas = dict()
    # <personas_tile> is a dictionary that contains the tile location of
    # the personas (!-> NOT px tile, but the actual tile coordinate).
    # The tile take the form of a set, (row, col). 
    # e.g., ["Isabella Rodriguez"] = (58, 39)
    self.personas_tile = dict()
    
    # # <persona_convo_match> is a dictionary that describes which of the two
    # # personas are talking to each other. It takes a key of a persona's full
    # # name, and value of another persona's full name who is talking to the 
    # # original persona. 
    # # e.g., dict["Isabella Rodriguez"] = ["Maria Lopez"]
    # self.persona_convo_match = dict()
    # # <persona_convo> contains the actual content of the conversations. It
    # # takes as keys, a pair of persona names, and val of a string convo. 
    # # Note that the key pairs are *ordered alphabetically*. 
    # # e.g., dict[("Adam Abraham", "Zane Xu")] = "Adam: baba \n Zane:..."
    # self.persona_convo = dict()

    # Loading in all personas. 
    init_env_file = f"{sim_folder}/environment/{str(self.step)}.json"
    init_env = json.load(open(init_env_file))
    for persona_name in reverie_meta['persona_names']: 
      persona_folder = f"{sim_folder}/personas/{persona_name}"
      p_x = init_env[persona_name]["x"]
      p_y = init_env[persona_name]["y"]
      curr_persona = Persona(persona_name, persona_folder)

      self.personas[persona_name] = curr_persona
      self.personas_tile[persona_name] = (p_x, p_y)
      self.maze.tiles[p_y][p_x]["events"].add(curr_persona.scratch
                                              .get_curr_event_and_desc())

    # REVERIE SETTINGS PARAMETERS:  
    # <server_sleep> denotes the amount of time that our while loop rests each
    # cycle; this is to not kill our machine. 
    self.server_sleep = 0.1

    # SIGNALING THE FRONTEND SERVER: 
    # curr_sim_code.json contains the current simulation code, and
    # curr_step.json contains the current step of the simulation. These are 
    # used to communicate the code and step information to the frontend. 
    # Note that step file is removed as soon as the frontend opens up the 
    # simulation. 
    curr_sim_code = dict()
    curr_sim_code["sim_code"] = self.sim_code
    with open(f"{fs_temp_storage}/curr_sim_code.json", "w") as outfile: 
      outfile.write(json.dumps(curr_sim_code, indent=2))
    
    curr_step = dict()
    curr_step["step"] = self.step
    with open(f"{fs_temp_storage}/curr_step.json", "w") as outfile: 
      outfile.write(json.dumps(curr_step, indent=2))

    # 创建movement文件夹
    os.makedirs(f"{sim_folder}/movement/", exist_ok=True)  # exist_ok=True 可以防止文件夹已存在时抛出错误


  def save(self): 
    """
    Save all Reverie progress -- this includes Reverie's global state as well
    as all the personas.  

    INPUT
      None
    OUTPUT 
      None
      * Saves all relevant data to the designated memory directory
    """
    sim_folder = f"{fs_storage}/{self.sim_code}"

    # 读取现有的 meta.json 文件
    reverie_meta_f = f"{sim_folder}/reverie/meta.json"
    try:
        with open(reverie_meta_f, 'r') as f:
            reverie_meta = json.load(f)
    except FileNotFoundError:
        reverie_meta = {
          "fork_sim_code": "No Fork",
          "start_date": "February 20, 2025",
          "curr_time": "February 20, 2025, 00:00:00",
          "sec_per_step": 10,
          "maze_name": "the_ville",
          "persona_names": [ 
          ],
          "step": 0,
          "owner": "",
          "parent": "No Fork",
          "pid": 0,
          "status": "not started",
          "total_step": 0
        }  # 如果文件不存在，初始化为模板配置

    # 更新字段
    reverie_meta["fork_sim_code"] = self.fork_sim_code
    reverie_meta["start_date"] = self.start_time.strftime("%B %d, %Y")
    reverie_meta["curr_time"] = self.curr_time.strftime("%B %d, %Y, %H:%M:%S")
    reverie_meta["sec_per_step"] = self.sec_per_step
    reverie_meta["maze_name"] = self.maze.maze_name
    reverie_meta["persona_names"] = list(self.personas.keys())
    reverie_meta["step"] = self.step
    reverie_meta["status"] = "running"  # 添加状态记录

    # 写回更新后的数据
    with open(reverie_meta_f, 'w') as outfile:
        json.dump(reverie_meta, outfile, ensure_ascii=False, indent=2)

    # Save the personas.
    for persona_name, persona in self.personas.items(): 
      save_folder = f"{sim_folder}/personas/{persona_name}/bootstrap_memory"
      persona.save(save_folder)


  def start_path_tester_server(self): 
    """
    Starts the path tester server. This is for generating the spatial memory
    that we need for bootstrapping a persona's state. 

    To use this, you need to open server and enter the path tester mode, and
    open the front-end side of the browser. 

    INPUT 
      None
    OUTPUT 
      None
      * Saves the spatial memory of the test agent to the path_tester_env.json
        of the temp storage. 
    """
    def print_tree(tree): 
      def _print_tree(tree, depth):
        dash = " >" * depth

        if type(tree) == type(list()): 
          if tree:
            print (dash, tree)
          return 

        for key, val in tree.items(): 
          if key: 
            print (dash, key)
          _print_tree(val, depth+1)
      
      _print_tree(tree, 0)

    # <curr_vision> is the vision radius of the test agent. Recommend 8 as 
    # our default. 
    curr_vision = 8
    # <s_mem> is our test spatial memory. 
    s_mem = dict()

    # The main while loop for the test agent. 
    while (True): 
      try: 
        curr_dict = {}
        tester_file = fs_temp_storage + "/path_tester_env.json"
        if check_if_file_exists(tester_file): 
          with open(tester_file) as json_file: 
            curr_dict = json.load(json_file)
            os.remove(tester_file)
          
          # Current camera location
          curr_sts = self.maze.sq_tile_size
          curr_camera = (int(math.ceil(curr_dict["x"]/curr_sts)), 
                         int(math.ceil(curr_dict["y"]/curr_sts))+1)
          curr_tile_det = self.maze.access_tile(curr_camera)

          # Initiating the s_mem
          world = curr_tile_det["world"]
          if curr_tile_det["world"] not in s_mem: 
            s_mem[world] = dict()

          # Iterating throughn the nearby tiles.
          nearby_tiles = self.maze.get_nearby_tiles(curr_camera, curr_vision)
          for i in nearby_tiles: 
            i_det = self.maze.access_tile(i)
            if (curr_tile_det["sector"] == i_det["sector"] 
                and curr_tile_det["arena"] == i_det["arena"]): 
              if i_det["sector"] != "": 
                if i_det["sector"] not in s_mem[world]: 
                  s_mem[world][i_det["sector"]] = dict()
              if i_det["arena"] != "": 
                if i_det["arena"] not in s_mem[world][i_det["sector"]]: 
                  s_mem[world][i_det["sector"]][i_det["arena"]] = list()
              if i_det["game_object"] != "": 
                if (i_det["game_object"] 
                    not in s_mem[world][i_det["sector"]][i_det["arena"]]):
                  s_mem[world][i_det["sector"]][i_det["arena"]] += [
                                                         i_det["game_object"]]

        # Incrementally outputting the s_mem and saving the json file. 
        print ("= " * 15)
        out_file = fs_temp_storage + "/path_tester_out.json"
        with open(out_file, "w") as outfile: 
          outfile.write(json.dumps(s_mem, indent=2))
        print_tree(s_mem)

      except:
        pass

      time.sleep(self.server_sleep * 10)


  def start_server(self, int_counter): 
    """
    Reverie 的主要后端服务器。 
    此函数从前端检索环境文件，以了解世界的状态，调用每个角色根据世界状态做出决策，并在特定步骤间隔保存他们的动作。 
    输入
      int_counter: 一个整数值，表示在本次迭代中剩余的步骤数。 
    输出 
      None
    """
    # <sim_folder> 指向当前模拟文件夹。
    sim_folder = f"{fs_storage}/{self.sim_code}"

    # 当角色到达游戏对象时，我们给该对象一个唯一事件。
    # 例如：('double studio[...]:bed', 'is', 'unmade', 'unmade')
    # 在这个周期结束之前，我们需要将其返回到初始状态，例如：
    # 例如：('double studio[...]:bed', None, None, None)
    # 所以我们需要跟踪我们添加了哪些事件。
    # <game_obj_cleanup> 用于此目的。
    game_obj_cleanup = dict()

    # Reverie 的主要循环。 
    while (True): 
      
        # 如果 <int_counter> 达到 0，则完成此次迭代。
        if int_counter == 0: 
            break

        # <curr_env_file> 文件是前端输出的文件。当前端完成其工作并移动角色时，它将放置一个新的环境文件，匹配我们的步骤计数。这时我们运行这个 for 循环的内容。否则，我们只需等待。
        curr_env_file = f"{sim_folder}/environment/{self.step}.json"
        if check_if_file_exists(curr_env_file):
            # 如果我们有一个环境文件，这意味着我们有新的感知输入给我们的角色。因此，我们首先检索它。
            try: 
                # 尝试保存块以增强循环的稳健性。
                with open(curr_env_file) as json_file:
                    new_env = json.load(json_file)
                    env_retrieved = True
            except: 
                pass
      
            if env_retrieved: 
                # 在这里，我们遍历 <game_obj_cleanup>，清理本周期中使用的所有对象动作。 
                for key, val in game_obj_cleanup.items(): 
                    # 我们将所有对象动作恢复为其空白形式（None）。
                    self.maze.turn_event_from_tile_idle(key, val)
                # 然后我们为本周期初始化 game_obj_cleanup。
                game_obj_cleanup = dict()

                # 我们首先在后端环境中移动我们的角色，以匹配前端环境。
                for persona_name, persona in self.personas.items(): 
                    # <curr_tile> 是角色之前所在的瓦片。
                    curr_tile = self.personas_tile[persona_name]
                    # <new_tile> 是角色现在将在此周期中移动到的瓦片。
                    new_tile = (new_env[persona_name]["x"], 
                                new_env[persona_name]["y"])

                    # 我们实际上在后端瓦片地图上移动角色。
                    self.personas_tile[persona_name] = new_tile
                    self.maze.remove_subject_events_from_tile(persona.name, curr_tile)
                    self.maze.add_event_from_tile(persona.scratch
                                                 .get_curr_event_and_desc(), new_tile)

                    # 现在，角色将旅行以到达他们的目的地。一旦
                    # 角色到达那里，我们激活对象动作。
                    if not persona.scratch.planned_path: 
                        # 我们将新的对象动作事件添加到后端瓦片地图上。
                        # 在其创建时，它存储在角色的后端中。
                        game_obj_cleanup[persona.scratch
                                         .get_curr_obj_event_and_desc()] = new_tile
                        self.maze.add_event_from_tile(persona.scratch
                                                       .get_curr_obj_event_and_desc(), new_tile)
                        # 我们还需要移除当前正在执行动作的对象的临时空白动作。
                        blank = (persona.scratch.get_curr_obj_event_and_desc()[0], 
                                 None, None, None)
                        self.maze.remove_event_from_tile(blank, new_tile)

                # 然后我们需要让每个角色感知和移动。每个角色的移动以 x y 坐标的形式出现，角色将朝向该方向移动。例如： (50, 34)
                # 这是角色核心思维被调用的地方。
                movements = {"persona": dict(), 
                             "meta": dict()}
                for persona_name, persona in self.personas.items(): 
                    # <next_tile> 是一个 x,y 坐标。例如：(58, 9)
                    # <pronunciatio> 是一个表情符号。例如："\ud83d\udca4"
                    # <description> 是移动的字符串描述。例如：
                    #   写她的下一个小说（编辑她的小说）
                    #   @ double studio:double studio:common room:sofa
                    next_tile, pronunciatio, description = persona.move(
                        self.maze, self.personas, self.personas_tile[persona_name], 
                        self.curr_time)
                    movements["persona"][persona_name] = {}
                    movements["persona"][persona_name]["movement"] = next_tile
                    movements["persona"][persona_name]["pronunciatio"] = pronunciatio
                    movements["persona"][persona_name]["description"] = description
                    movements["persona"][persona_name]["chat"] = (persona
                                                                  .scratch.chat)

                # 在移动字典中包含当前阶段的元信息。
                movements["meta"]["curr_time"] = (self.curr_time 
                                                   .strftime("%B %d, %Y, %H:%M:%S"))

                # 然后我们将角色的移动写入一个文件，该文件将被发送到前端服务器。
                # 示例 JSON 输出：
                # {"persona": {"Maria Lopez": {"movement": [58, 9]}},
                #  "persona": {"Klaus Mueller": {"movement": [38, 12]}}, 
                #  "meta": {curr_time: <datetime>}}
                curr_move_path = f"{sim_folder}/movement"
                if not os.path.exists(curr_move_path):
                    os.makedirs(curr_move_path)
                curr_move_file = f"{sim_folder}/movement/{self.step}.json"
                with open(curr_move_file, "w") as outfile: 
                    outfile.write(json.dumps(movements, indent=2))

                # 在此周期之后，世界向前迈出一步，当前时间按 <sec_per_step> 的量移动。
                self.step += 1
                self.curr_time += datetime.timedelta(seconds=self.sec_per_step)

                int_counter -= 1
        # 睡眠以避免消耗机器资源。
        time.sleep(self.server_sleep)


  def open_server(self, input_command: str = None) -> None: 
    """
    打开一个交互式终端提示，允许你逐步运行模拟并探查智能体状态。

    输入 
      None
    输出
      None
    """
    print ("Note: The agents in this simulation package are computational")
    print ("constructs powered by generative agents architecture and LLM. We")
    print ("clarify that these agents lack human-like agency, consciousness,")
    print ("and independent decision-making.\n---")

    # <sim_folder> 指向当前模拟文件夹。
    sim_folder = f"{fs_storage}/{self.sim_code}"

    while True: 
        if not input_command:
            sim_command = input("Input Option: ")
        else:
            sim_command = input_command
        sim_command = sim_command.strip()
        ret_str = ""

        try: 
            if sim_command.lower() in ["f", "fin", "finish", "save and finish"]: 
                # 完成模拟环境并保存进度。 
                # 示例：fin
                self.save()
                break

            elif sim_command.lower() == "start path tester mode": 
                # 启动路径测试器并删除当前的分叉模拟文件。
                # 注意，一旦启动此模式，需退出会话并重新启动才能运行其他内容。
                shutil.rmtree(sim_folder) 
                self.start_path_tester_server()

            elif sim_command.lower() == "exit": 
                # 完成模拟环境但不保存进度，并删除当前模拟的所有保存数据。
                # 示例：exit 
                shutil.rmtree(sim_folder) 
                break 

            elif sim_command.lower() == "save": 
                # 保存当前模拟进度。 
                # 示例：save
                self.save()

            elif sim_command[:3].lower() == "run": 
                # 运行提示中指定的步骤数。
                # 示例：run 1000
                int_count = int(sim_command.split()[-1])
                self.start_server(int_count)

            elif ("print persona schedule" 
                  in sim_command[:22].lower()): 
                # 打印指定角色的分解日程。
                # 示例：print persona schedule Isabella Rodriguez
                ret_str += (self.personas[" ".join(sim_command.split()[-2:])]
                            .scratch.get_str_daily_schedule_summary())

            elif ("print all persona schedule" 
                  in sim_command[:26].lower()): 
                # 打印世界中所有角色的分解日程。 
                # 示例：print all persona schedule
                for persona_name, persona in self.personas.items(): 
                    ret_str += f"{persona_name}\n"
                    ret_str += f"{persona.scratch.get_str_daily_schedule_summary()}\n"
                    ret_str += f"---\n"

            elif ("print hourly org persona schedule" 
                  in sim_command.lower()): 
                # 打印指定角色的小时日程。
                # 这个显示的是原始的、未分解的日程。
                # 示例：print hourly org persona schedule Isabella Rodriguez
                ret_str += (self.personas[" ".join(sim_command.split()[-2:])]
                            .scratch.get_str_daily_schedule_hourly_org_summary())

            elif ("print persona current tile" 
                  in sim_command[:26].lower()): 
                # 打印指定角色的 x y 瓦片坐标。 
                # 示例：print persona current tile Isabella Rodriguez
                ret_str += str(self.personas[" ".join(sim_command.split()[-2:])]
                            .scratch.curr_tile)

            elif ("print persona chatting with buffer" 
                  in sim_command.lower()): 
                # 打印指定角色的聊天缓冲区。
                # 示例：print persona chatting with buffer Isabella Rodriguez
                curr_persona = self.personas[" ".join(sim_command.split()[-2:])]
                for p_n, count in curr_persona.scratch.chatting_with_buffer.items(): 
                    ret_str += f"{p_n}: {count}"

            elif ("print persona associative memory (event)" 
                  in sim_command.lower()):
                # 打印指定角色的联想记忆（事件）。
                # 示例：print persona associative memory (event) Isabella Rodriguez
                ret_str += f'{self.personas[" ".join(sim_command.split()[-2:])]}\n'
                ret_str += (self.personas[" ".join(sim_command.split()[-2:])]
                                           .a_mem.get_str_seq_events())

            elif ("print persona associative memory (thought)" 
                  in sim_command.lower()): 
                # 打印指定角色的联想记忆（思想）。
                # 示例：print persona associative memory (thought) Isabella Rodriguez
                ret_str += f'{self.personas[" ".join(sim_command.split()[-2:])]}\n'
                ret_str += (self.personas[" ".join(sim_command.split()[-2:])]
                                           .a_mem.get_str_seq_thoughts())

            elif ("print persona associative memory (chat)" 
                  in sim_command.lower()): 
                # 打印指定角色的联想记忆（聊天）。
                # 示例：print persona associative memory (chat) Isabella Rodriguez
                ret_str += f'{self.personas[" ".join(sim_command.split()[-2:])]}\n'
                ret_str += (self.personas[" ".join(sim_command.split()[-2:])]
                                           .a_mem.get_str_seq_chats())

            elif ("print persona spatial memory" 
                  in sim_command.lower()): 
                # 打印指定角色的空间记忆。
                # 示例：print persona spatial memory Isabella Rodriguez
                self.personas[" ".join(sim_command.split()[-2:])].s_mem.print_tree()

            elif ("print current time" 
                  in sim_command[:18].lower()): 
                # 打印世界的当前时间。 
                # 示例：print current time
                ret_str += f'{self.curr_time.strftime("%B %d, %Y, %H:%M:%S")}\n'
                ret_str += f'步骤: {self.step}'

            elif ("print tile event" 
                  in sim_command[:16].lower()): 
                # 打印指定瓦片中的事件。
                # 示例：print tile event 50, 30
                cooordinate = [int(i.strip()) for i in sim_command[16:].split(",")]
                for i in self.maze.access_tile(cooordinate)["events"]: 
                    ret_str += f"{i}\n"

            elif ("print tile details" 
                  in sim_command.lower()): 
                # 打印指定瓦片的详细信息。
                # 示例：print tile details 50, 30
                cooordinate = [int(i.strip()) for i in sim_command[18:].split(",")]
                for key, val in self.maze.access_tile(cooordinate).items(): 
                    ret_str += f"{key}: {val}\n"

            elif ("call -- analysis" 
                  in sim_command.lower()): 
                # 启动与智能体的无状态聊天会话。不会将任何内容保存到智能体的记忆中。 
                # 示例：call -- analysis Isabella Rodriguez
                persona_name = sim_command[len("call -- analysis"):].strip() 
                self.personas[persona_name].open_convo_session("analysis")

            elif ("call -- load history" 
                  in sim_command.lower()): 
                curr_file = maze_assets_loc + "/" + sim_command[len("call -- load history"):].strip() 
                # 示例：call -- load history the_ville/agent_history_init_n3.csv

                rows = read_file_to_list(curr_file, header=True, strip_trail=True)[1]
                clean_whispers = []
                for row in rows: 
                    agent_name = row[0].strip() 
                    whispers = row[1].split(";")
                    whispers = [whisper.strip() for whisper in whispers]
                    for whisper in whispers: 
                        clean_whispers += [[agent_name, whisper]]

                load_history_via_whisper(self.personas, clean_whispers)

            print(ret_str)
        
        except Exception as e:
            print("(reverie): Error: ", e)
            # 删除当前步骤的移动文件（如果存在）
            movement_file = f"{sim_folder}/movement/{self.step}.json"
            if os.path.exists(movement_file):
                os.remove(movement_file)
                print(f"(reverie): Removed movement file: {movement_file}")
            # 确保初始环境配置文件 0.json 始终存在
            if self.step > 0:
                env_file = f"{sim_folder}/environment/{self.step}.json"
                if os.path.exists(env_file):
                    os.remove(env_file)
                    print(f"(reverie): Removed environment file: {env_file}")

            print(f"(reverie): An error occurred in step {self.step}")
            # 回退一步
            self.step -= 1
            if self.step < 0:
                self.step = 0
            # 更新当前时间
            self.curr_time -= datetime.timedelta(seconds=self.sec_per_step)
            # 抛出异常，包含当前步骤信息
            raise Exception(e, self.step)
        else:
            # 如果传入了输入命令，则执行一个命令后退出。
            if input_command:
                break

if __name__ == '__main__':

  # Pars input params
  parser = argparse.ArgumentParser(description='Reverie Server')
  parser.add_argument(
    '--origin',
    type=str,
    default="base_the_ville_isabella_maria_klaus",
    help='The name of the forked simulation'
  )
  parser.add_argument(
    '--target',
    type=str,
    default="test-simulation",
    help='The name of the new simulation'
  )
    
  origin = parser.parse_args().origin
  target = parser.parse_args().target
  
  rs = ReverieServer(origin, target)
  rs.open_server()




















































