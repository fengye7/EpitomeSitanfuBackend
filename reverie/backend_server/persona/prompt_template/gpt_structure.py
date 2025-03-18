# 项目原件副本

"""
Author: Joon Sung Park (joonspk@stanford.edu)

File: gpt_structure.py
Description: Wrapper functions for calling OpenAI APIs.
"""
import time 
import json
from pathlib import Path
from openai import AzureOpenAI, OpenAI

from persona.prompt_template.sparkai_embedding import get_sparkai_embedding
from utils import *
from openai_cost_logger import DEFAULT_LOG_PATH
from persona.prompt_template.openai_logger_singleton import OpenAICostLogger_Singleton

# # 设置代理环境变量,以便VPN起作用
# import os
# os.environ["HTTP_PROXY"] = "http://127.0.0.1:7890"
# os.environ["HTTPS_PROXY"] = "http://127.0.0.1:7890"

config_path = os.path.join(ROOT_DIR,"openai_config copy.json")
with open(config_path, "r") as f:
    llm_configs = json.load(f) 

openai_config = llm_configs["clients"].get(llm_configs["client"]) # 选择模型相应的配置
# print(openai_config)

def setup_client(type: str, config: dict):
  """Setup the OpenAI client.

  Args:
      type (str): the type of client. Either "azure" or "openai".
      config (dict): the configuration for the client.

  Raises:
      ValueError: if the client is invalid.

  Returns:
      The client object created, either AzureOpenAI or OpenAI.
  """
  if type == "azure":
    print("正在使用azure!")
    client = AzureOpenAI(
        azure_endpoint=config["endpoint"],
        api_key=config["key"],
        api_version=config["api-version"],
    )
  elif type == "openai":
    print("正在使用openai!")
    client = OpenAI(
        api_key=config["key"],
    )
  elif type == "openai-transfer": # 国内中转openai
    print("正在使用国内中转链接！")
    client = OpenAI(
        api_key = config["key"],
        base_url = config["url"] 
    )
  elif type == "sparkai": # 国内中转openai
    print("正在使用星火大模型！")
    client = OpenAI(
        api_key = config["key"],
        base_url = config["url"] # 指向讯飞星火的请求地址
    )
  else:
    raise ValueError("Invalid client")
  return client

if openai_config["client"] == "azure":
  client = setup_client("azure", {
      "endpoint": openai_config["model-endpoint"],
      "key": openai_config["model-key"],
      "api-version": openai_config["model-api-version"],
  })
elif openai_config["client"] == "openai":
  client = setup_client("openai", { "key": openai_config["model-key"] })
elif openai_config["client"] == "openai-transfer":
  client = setup_client("openai-transfer", {"key": openai_config["model-key"],
                                            "url":openai_config["url"]})
elif openai_config["client"] == "sparkai":
  client = setup_client("sparkai", {"key": openai_config["sparkai-apipassword"],
                                    "url":openai_config["sparkai-openai-url"]})

if openai_config["embeddings-client"] == "azure":  
  embeddings_client = setup_client("azure", {
      "endpoint": openai_config["embeddings-endpoint"],
      "key": openai_config["embeddings-key"],
      "api-version": openai_config["embeddings-api-version"],
  })
elif openai_config["embeddings-client"] == "openai":
  embeddings_client = setup_client("openai", { "key": openai_config["embeddings-key"] })
elif openai_config["embeddings-client"] == "openai-transfer":
  embeddings_client = setup_client("openai-transfer", { "key": openai_config["embeddings-key"],
                                                      "url":openai_config["embeddings-url"]})
elif openai_config["embeddings-client"] == "sparkai":
  embeddings_client = setup_client("sparkai", {"key": openai_config["sparkai-apipassword"], # 实际不能使用，在后续get_embedding中处理
                                    "url":openai_config["sparkai-openai-url"]})
else:
  raise ValueError("Invalid embeddings client")

cost_logger = OpenAICostLogger_Singleton(
  experiment_name = openai_config["experiment-name"],
  log_folder = DEFAULT_LOG_PATH,
  cost_upperbound = openai_config["cost-upperbound"]
)


def temp_sleep(seconds=0.1):
  time.sleep(seconds)


def ChatGPT_single_request(prompt): 
  temp_sleep()
  completion = client.chat.completions.create(
    model=openai_config["model"],
    messages=[{"role": "user", "content": prompt}]
  )
  # cost_logger.update_cost(completion, input_cost=openai_config["model-costs"]["input"], output_cost=openai_config["model-costs"]["output"])
  return completion.choices[0].message.content


def ChatGPT_request(prompt): 
  """
  Given a prompt and a dictionary of GPT parameters, make a request to OpenAI
  server and returns the response. 
  ARGS:
    prompt: a str prompt
    gpt_parameter: a python dictionary with the keys indicating the names of  
                   the parameter and the values indicating the parameter 
                   values.   
  RETURNS: 
    a str of GPT-3's response. 
  """
  # temp_sleep()
  try: 
    completion = client.chat.completions.create(
    model=openai_config["model"],
    messages=[{"role": "user", "content": prompt}]
    )
    # cost_logger.update_cost(completion, input_cost=openai_config["model-costs"]["input"], output_cost=openai_config["model-costs"]["output"])
    return completion.choices[0].message.content
  
  except Exception as e: 
    print(f"Error: {e}")
    return "ChatGPT ERROR"


def ChatGPT_safe_generate_response(prompt, 
                                   example_output,
                                   special_instruction,
                                   repeat=3,
                                   fail_safe_response="error",
                                   func_validate=None,
                                   func_clean_up=None,
                                   verbose=False): 
  # prompt = 'GPT-3 Prompt:\n"""\n' + prompt + '\n"""\n'
  prompt = '"""\n' + prompt + '\n"""\n'
  prompt += f"Output the response to the prompt above in json. {special_instruction}\n"
  prompt += "Example output json:\n"
  prompt += '{"output": "' + str(example_output) + '"}'

  if verbose: 
    print ("CHAT GPT PROMPT")
    print (prompt)

  for i in range(repeat): 

    try: 
      curr_gpt_response = ChatGPT_request(prompt).strip()
      end_index = curr_gpt_response.rfind('}') + 1
      curr_gpt_response = curr_gpt_response[:end_index]
      curr_gpt_response = json.loads(curr_gpt_response)["output"]
      
      if func_validate(curr_gpt_response, prompt=prompt): 
        return func_clean_up(curr_gpt_response, prompt=prompt)
      
      if verbose: 
        print ("---- repeat count: \n", i, curr_gpt_response)
        print (curr_gpt_response)
        print ("~~~~")

    except: 
      pass

  return False


def ChatGPT_safe_generate_response_OLD(prompt, 
                                   repeat=3,
                                   fail_safe_response="error",
                                   func_validate=None,
                                   func_clean_up=None,
                                   verbose=False): 
  if verbose: 
    print ("CHAT GPT PROMPT")
    print (prompt)

  for i in range(repeat): 
    try: 
      curr_gpt_response = ChatGPT_request(prompt).strip()
      if func_validate(curr_gpt_response, prompt=prompt): 
        return func_clean_up(curr_gpt_response, prompt=prompt)
      if verbose: 
        print (f"---- repeat count: {i}")
        print (curr_gpt_response)
        print ("~~~~")

    except: 
      pass
  print ("FAIL SAFE TRIGGERED") 
  return fail_safe_response


def GPT_request(prompt, gpt_parameter): 
  """
  Given a prompt and a dictionary of GPT parameters, make a request to OpenAI
  server and returns the response. 
  ARGS:
    prompt: a str prompt
    gpt_parameter: a python dictionary with the keys indicating the names of  
                   the parameter and the values indicating the parameter 
                   values.   
  RETURNS: 
    a str of GPT-3's response. 
  """
  temp_sleep()
  try: 
    messages = [{
      "role": "system", "content": prompt
    }]
    response = client.chat.completions.create(
                model=gpt_parameter["engine"],
                messages=messages,
                temperature=gpt_parameter["temperature"],
                max_tokens=gpt_parameter["max_tokens"],
                top_p=gpt_parameter["top_p"],
                frequency_penalty=gpt_parameter["frequency_penalty"],
                presence_penalty=gpt_parameter["presence_penalty"],
                stream=gpt_parameter["stream"],
                stop=gpt_parameter["stop"],)
    # cost_logger.update_cost(response=response, input_cost=openai_config["model-costs"]["input"], output_cost=openai_config["model-costs"]["output"])
    return response.choices[0].message.content
  except Exception as e:
    print(f"Error: {e}")
    return "TOKEN LIMIT EXCEEDED"


def generate_prompt(curr_input, prompt_lib_file): 
  """
  Takes in the current input (e.g. comment that you want to classifiy) and 
  the path to a prompt file. The prompt file contains the raw str prompt that
  will be used, which contains the following substr: !<INPUT>! -- this 
  function replaces this substr with the actual curr_input to produce the 
  final promopt that will be sent to the GPT3 server. 
  ARGS:
    curr_input: the input we want to feed in (IF THERE ARE MORE THAN ONE
                INPUT, THIS CAN BE A LIST.)
    prompt_lib_file: the path to the promopt file. 
  RETURNS: 
    a str prompt that will be sent to OpenAI's GPT server.  
  """
  if type(curr_input) == type("string"): 
    curr_input = [curr_input]
  curr_input = [str(i) for i in curr_input]

  f = open(prompt_lib_file, "r")
  prompt = f.read()
  f.close()
  for count, i in enumerate(curr_input):   
    prompt = prompt.replace(f"!<INPUT {count}>!", i)
  if "<commentblockmarker>###</commentblockmarker>" in prompt: 
    prompt = prompt.split("<commentblockmarker>###</commentblockmarker>")[1]
  return prompt.strip()


def safe_generate_response(prompt, 
                           gpt_parameter,
                           repeat=5,
                           fail_safe_response="error",
                           func_validate=None,
                           func_clean_up=None,
                           verbose=False): 
  if verbose: 
    print (prompt)

  for i in range(repeat): 
    curr_gpt_response = GPT_request(prompt, gpt_parameter)
    try:
      if func_validate(curr_gpt_response, prompt=prompt): 
        return func_clean_up(curr_gpt_response, prompt=prompt)
      if verbose: 
        print ("---- repeat count: ", i, curr_gpt_response)
        print (curr_gpt_response)
        print ("~~~~")
    except:
      pass
  return fail_safe_response


def get_embedding(text, model=openai_config["embeddings"]):
  # print("嵌入向量化输入：",text)
  text = text.replace("\n", " ")
  if not text: 
    text = "this is blank"
  # response = embeddings_client.embeddings.create(input=[text], model=model)
  # # cost_logger.update_cost(response=response, input_cost=openai_config["embeddings-costs"]["input"], output_cost=openai_config["embeddings-costs"]["output"])
  # # print("嵌入向量化输出：",response.data[0].embedding)
  # return response.data[0].embedding
  if openai_config["embeddings-client"] == "sparkai":
    # version-1
    # response = embeddings_client.embedding(text=text, kind='text')
    # print("嵌入向量化输出：",response)
    # return response

    # version-2
    # for attempt in range(3):
    #   try:
    #       response = embeddings_client.embedding(text=text, kind='text')
    #       return response
    #       break
    #   except ValueError as e:
    #       print(f"Attempt {attempt+1} failed: {e}")
    #       time.sleep(2)  # Wait before retrying

    # version-3
    response = get_sparkai_embedding(text=text,style=openai_config["embeddings-domin"])
    # print("嵌入向量化输出：",response)
    return response
  else:
    response = embeddings_client.embeddings.create(input=[text], model=model)
    cost_logger.update_cost(response=response, input_cost=openai_config["embeddings-costs"]["input"], output_cost=openai_config["embeddings-costs"]["output"])
    return response.data[0].embedding


if __name__ == '__main__':
  gpt_parameter = {"engine": openai_config["model"], "max_tokens": 50, 
                   "temperature": 0, "top_p": 1, "stream": False,
                   "frequency_penalty": 0, "presence_penalty": 0, 
                   "stop": ['"']}
  curr_input = ["driving to a friend's house"]
  prompt_lib_file = "prompt_template/test_prompt_July5.txt"
  prompt = generate_prompt(curr_input, prompt_lib_file)

  def __func_validate(gpt_response): 
    if len(gpt_response.strip()) <= 1:
      return False
    if len(gpt_response.strip().split(" ")) > 1: 
      return False
    return True
  def __func_clean_up(gpt_response):
    cleaned_response = gpt_response.strip()
    return cleaned_response

  output = safe_generate_response(prompt, 
                                 gpt_parameter,
                                 5,
                                 "rest",
                                 __func_validate,
                                 __func_clean_up,
                                 True)

  print (output)


