import asyncio
from asyncio.log import logger
from enum import Enum
import json
import logging
import os
import re
import signal
import subprocess
import threading
from django.core.cache  import cache
import psutil
from rest_framework.views  import APIView
from rest_framework.response  import Response
from rest_framework import status
from rest_framework.permissions  import AllowAny
from drf_yasg.utils  import swagger_auto_schema
from drf_yasg import openapi
from django.conf  import settings
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

from global_methods import *
from global_methods import MyCopyanything

import sys


# 添加 reverie 模块的父目录到 sys.path
sys.path.append(os.path.join(settings.ROOT_DIR, 'reverie'))
# from automatic_execution import AutomaticReverieServer
from compress_sim_storage import compress
# from reverie import ReverieServer

EXPERIMENT_STORAGE_ROOT = settings.EXPERIMENT_STORAGE_ROOT
PUBLIC_EXPERIMENT_WHITELIST = settings.PUBLIC_EXPERIMENT_WHITELIST
BASE_DIR = settings.BASE_DIR

from rest_framework.response import Response
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
import os
from django.core.cache import cache

# 匹配前端定义 ResultEnum
class ResultEnum:
    SUCCESS = 0
    ERROR = 500
    OVERDUE = 9009
    TIMEOUT = 10000
    TYPE = 'success'

class ExperimentStatus(Enum):
    NOT_STARTED = "not started"
    RUNNING = "running"
    FINISHED = "finished"

def generate_response(code, message, data):
    """ 生成统一格式的响应 """
    response = Response({
        "code": code,
        "message": message,
        "data": data
    })  # 处理状态码

    # 添加 CORS 头
    response["Access-Control-Allow-Origin"] = "*"
    response["Access-Control-Allow-Headers"] = "Content-Type"
    response["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"

    return response



class ExperimentListView(APIView):
    """
    实验列表视图（支持公共和个性化实验查询）
    """
    permission_classes = [AllowAny]

    def _get_experiments(self):
        """ 获取实验列表"""
        experiments = []  # 初始化变量
        try:
            experiments = os.listdir(EXPERIMENT_STORAGE_ROOT)
        except FileNotFoundError:
            return generate_response(ResultEnum.ERROR, "实验存储目录不存在", None)
        except PermissionError:
            return generate_response(ResultEnum.ERROR, "目录访问权限不足", None)
        return experiments

    def _get_experiment_metadata(self, experiment_name):
        """ 获取实验的元数据 """
        experiment_dir = os.path.join(EXPERIMENT_STORAGE_ROOT, experiment_name)
        reverie_meta_path = os.path.join(experiment_dir, "reverie/meta.json")
        try:
            with open(reverie_meta_path, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            return None

    def _build_experiment_hierarchy(self, experiments, username):
        """ 构建实验层级关系 """
        experiments_map = {}  # 存储所有实验对象
        parent_map = {}  # 存储父实验与子实验的关系

        for exp in experiments:
            metadata = self._get_experiment_metadata(exp)
            if metadata is None:
                continue  # 忽略不存在的实验

            is_public = exp in PUBLIC_EXPERIMENT_WHITELIST
            if not is_public and username != metadata.get('owner'):
                continue  # 不是公共实验且不是当前用户的实验，过滤掉

            parent = metadata.get('parent')
            is_template = (parent == exp)  # 父实验就是自己的视为模板

            # 创建实验对象
            experiment_info = {
                'name': exp,
                'type': 'public' if is_public else 'private',
                'status': metadata.get('status', 'not started'),
                'current_step': metadata.get('current_step', 0),
                'isTemplate': is_template,
                'children': []
            }

            # 存储实验对象
            experiments_map[exp] = experiment_info

            # 组织父子关系
            if not is_template:
                if parent not in parent_map:
                    parent_map[parent] = []
                parent_map[parent].append(experiment_info)

        # 将子实验正确归入父实验
        for parent, children in parent_map.items():
            if parent in experiments_map:
                experiments_map[parent]['children'].extend(children)

        # 第三步：返回所有 `isTemplate` 为 True 的实验（即顶级实验）
        return [exp for exp in experiments_map.values() if exp['isTemplate']]


    @swagger_auto_schema(
        operation_description="获取实验列表（公共和个性化实验查询）",
        manual_parameters=[
            openapi.Parameter('username', openapi.IN_QUERY, description="用户名", type=openapi.TYPE_STRING)
        ],
        responses={
            ResultEnum.SUCCESS: openapi.Response(
                description="成功获取实验列表",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'code': openapi.Schema(type=openapi.TYPE_INTEGER),
                        'message': openapi.Schema(type=openapi.TYPE_STRING),
                        'data': openapi.Schema(
                            type=openapi.TYPE_ARRAY,
                            items=openapi.Items(type=openapi.TYPE_OBJECT, properties={
                                'name': openapi.Schema(type=openapi.TYPE_STRING),
                                'type': openapi.Schema(type=openapi.TYPE_STRING),
                                'status': openapi.Schema(type=openapi.TYPE_STRING),
                                'current_step': openapi.Schema(type=openapi.TYPE_INTEGER),
                                'isTemplate': openapi.Schema(type=openapi.TYPE_BOOLEAN),
                                'children': openapi.Schema(type=openapi.TYPE_ARRAY, items=openapi.Items(type=openapi.TYPE_OBJECT))
                            })
                        ),
                    }
                )
            ),
            ResultEnum.ERROR: openapi.Response(
                description="错误信息",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'code': openapi.Schema(type=openapi.TYPE_INTEGER),
                        'message': openapi.Schema(type=openapi.TYPE_STRING)
                    }
                )
            )
        }
    )
    def get(self, request, *args, **kwargs):
        """ 统一入口处理 GET 请求 """
        username = request.query_params.get('username', '')  # 获取用户名参数
        try:
            experiments = self._get_experiments()

            if isinstance(experiments, Response):  # 检查是否返回了错误响应
                return experiments

            all_experiments = self._build_experiment_hierarchy(experiments, username)

            return generate_response(
                ResultEnum.SUCCESS,
                "成功获取实验列表",
                all_experiments  # 直接返回处理后的实验列表
            )

        except Exception as e:
            error_type = type(e).__name__
            status_code = ResultEnum.ERROR if not isinstance(e, ValueError) else ResultEnum.ERROR
            return generate_response(
                status_code,
                f"{error_type}: {str(e)}",
                None  # 在错误情况下，返回 None 或详细错误信息
            )
        
class CompressSimulationView(APIView):
    """
    压缩实验接口
    接受实验名称作为参数，并进行压缩处理
    """
    permission_classes = [AllowAny]

    @swagger_auto_schema(
        operation_description="压缩实验",
        manual_parameters=[
            openapi.Parameter('sim_code', openapi.IN_QUERY, description="实验名称，用于指定需要压缩的实验，例如：base_the_ville_isabella_maria_klaus", type=openapi.TYPE_STRING, required=True)
        ],
        responses={
            200: openapi.Response(description="压缩成功", examples={"application/json": {"message": "Compression successful"}}),
            400: openapi.Response(description="参数验证失败", examples={"application/json": {"error": "Invalid sim_code value"}}),
            500: openapi.Response(description="服务器内部错误", examples={"application/json": {"error": "Compression failed"}})
        }
    )
    def post(self, request):
        """
        核心逻辑：
        1. 参数验证与处理
        2. 调用压缩函数
        3. 返回结果
        """
        sim_code = request.GET.get('sim_code', '')

        # 验证参数
        if not sim_code or not isinstance(sim_code, str):
            return Response({"error": "Invalid sim_code value"}, status=400)

        try:
            # 调用压缩函数
            compress(sim_code)
            return generate_response(ResultEnum.SUCCESS, "Compression successful", {})
        except FileExistsError:
            # 文件已存在，返回成功消息但包含提示
            return generate_response(ResultEnum.SUCCESS, "Compression completed, but files already exist.", {})
        except Exception as e:
            # 处理其他异常
            return generate_response(ResultEnum.ERROR, {"error": str(e)}, {})
    
class VideoHLSView(APIView):
    """
    HLS视频切片生成服务接口{废弃接口}
    访问示例：GET /api/hls/generate/?video_path=/media/videos/source.mp4&segment_duration=10
    """
    permission_classes = [AllowAny]

    @swagger_auto_schema(
        operation_description="获取视频切片并通过 HLS 协议播放{废弃接口}",
        manual_parameters=[
            openapi.Parameter('video_path', openapi.IN_QUERY, description="视频文件路径，用于切割和生成 HLS 流", type=openapi.TYPE_STRING, default='path/to/video.mp4'),
            openapi.Parameter('segment_duration', openapi.IN_QUERY, description="每个视频切片的时长，单位秒（默认10秒）", type=openapi.TYPE_INTEGER, default=10)
        ],
        responses={
            ResultEnum.SUCCESS: openapi.Response(description="HLS 播放器嵌入信息", content={'text/html': {}}),
            ResultEnum.ERROR: openapi.Response(description="参数验证失败/视频处理失败", examples={"application/json": {"error": "Invalid video path"}}),
            ResultEnum.TIMEOUT: openapi.Response(description="视频处理超时", examples={"application/json": {}})
        }
    )
    def get(self, request):
        """
        核心逻辑：
        1. 参数验证与处理 
        2. 使用 FFmpeg 将视频切割成 .ts 文件并生成 .m3u8 播放列表
        3. 动态模板渲染，生成可以嵌入 iframe 的 HLS 播放器
        """
        video_path = request.GET.get('video_path')
        segment_duration = int(request.GET.get('segment_duration', 10))

        if not video_path or not os.path.exists(video_path):
            return generate_response(ResultEnum.ERROR, "参数验证失败", {"error": "Invalid video path"})

        # 生成输出目录结构
        video_dir = os.path.dirname(video_path)
        base_name = os.path.splitext(os.path.basename(video_path))[0]
        output_dir = os.path.join(video_dir, f"{base_name}_hls")
        os.makedirs(output_dir, exist_ok=True)

        # HLS转码参数
        m3u8_path = os.path.join(output_dir, 'playlist.m3u8')
        ffmpeg_command = [
            'ffmpeg',
            '-i', video_path,
            '-vf', "scale=ceil(iw/2)*2:ceil(ih/2)*2",  # 自动修正尺寸
            '-c:v', 'libx264',
            '-profile:v', 'main',
            '-crf', '23',
            '-preset', 'medium',
            '-c:a', 'aac',
            '-b:a', '128k',
            '-f', 'hls',
            '-hls_time', str(segment_duration),
            '-hls_list_size', '0',
            '-hls_segment_filename', os.path.join(output_dir, 'segment_%03d.ts'),
            '-hls_flags', 'independent_segments',
            m3u8_path
        ]

        # 执行转码
        try:
            result = subprocess.run(
                ffmpeg_command,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=300  # 5分钟超时
            )
            logger.info(f"HLS转码成功: {result.stdout}")
        except subprocess.TimeoutExpired:
            logger.error("HLS转码超时")
            return generate_response(ResultEnum.TIMEOUT, "视频处理超时", {})
        except subprocess.CalledProcessError as e:
            logger.error(f"HLS转码失败: {e.stdout}")
            return generate_response(ResultEnum.ERROR, "视频处理失败", {"detail": e.stdout})

        # 生成访问URL
        relative_path = os.path.relpath(m3u8_path, settings.MEDIA_ROOT)
        m3u8_url = f"{settings.MEDIA_URL}{relative_path}"

        return generate_response(ResultEnum.SUCCESS, "成功生成HLS播放列表", {
            "playlist_url": m3u8_url,
            "segment_duration": segment_duration,
            "resolution": "1280x720 (保持宽高比)",
            "codec": "H.264 + AAC",
            "expire_time": "24h"
        })


class ExperimentCreateView(APIView):
    """
    创建或修改实验
    包括设置人物、描述、行为、地图等
    """
    permission_classes = [AllowAny]

    @swagger_auto_schema(
        operation_description="创建实验，仅仅创建实验模板，启动方式仍采用start接口通过保留模板创建新文件夹的方式启动",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'sim_code': openapi.Schema(type=openapi.TYPE_STRING, description="实验名称，例如：base_the_ville_isabella_maria_klaus"),
                'maze_name': openapi.Schema(type=openapi.TYPE_STRING, default="the_ville",description="实验地图：the_ville"),
                "start_date": openapi.Schema(type=openapi.TYPE_STRING, default="February 20, 2025",description="实验设定的开始日期，例如：February 20, 2025"),
                'characters': openapi.Schema(
                    type=openapi.TYPE_ARRAY,
                    items=openapi.Items(
                        type=openapi.TYPE_OBJECT,
                        properties={
                            'name': openapi.Schema(type=openapi.TYPE_STRING, description="人物名称"),
                            'first_name': openapi.Schema(type=openapi.TYPE_STRING, description="人物的名字"),
                            'last_name': openapi.Schema(type=openapi.TYPE_STRING, description="人物的姓氏"),
                            'age': openapi.Schema(type=openapi.TYPE_INTEGER, description="人物的年龄"),
                            'daily_plan_req': openapi.Schema(type=openapi.TYPE_STRING, description="人物的日常计划"),
                            'innate': openapi.Schema(type=openapi.TYPE_STRING, description="人物的天性"),
                            'learned': openapi.Schema(type=openapi.TYPE_STRING, description="人物的学习经验"),
                            'currently': openapi.Schema(type=openapi.TYPE_STRING, description="人物当前的状态"),
                            'lifestyle': openapi.Schema(type=openapi.TYPE_STRING, description="人物的生活方式"),
                            'living_area': openapi.Schema(type=openapi.TYPE_STRING, description="人物的居住区域"),
                            'coordinates_x': openapi.Schema(type=openapi.TYPE_INTEGER, description="人物初始x坐标(0~140)"),
                            'coordinates_y': openapi.Schema(type=openapi.TYPE_INTEGER, description="人物初始y坐标(0~100)"),
                        }
                    ),
                    description="人物设置，包括每个人物的详细信息"
                ),
                'steps': openapi.Schema(type=openapi.TYPE_INTEGER, description="实验模拟的步数"),
                'sec_per_step':openapi.Schema(type=openapi.TYPE_INTEGER, description="实验每模拟一步代表的秒数"),
                'owner': openapi.Schema(type=openapi.TYPE_STRING, description="所属者名称: 例如：ZhouChengjie"),
            },
        ),
        responses={
            ResultEnum.SUCCESS: openapi.Response(description="实验创建成功"),
            ResultEnum.ERROR: openapi.Response(description="参数验证失败，确保所有必需字段均已提供"),
        }
    )
    def post(self, request):
        """
        创建或修改实验
        """
        # 获取参数
        sim_code = request.data.get('sim_code')
        maze_name = request.data.get('maze_name')
        start_date = request.data.get('start_date')
        characters = request.data.get('characters')
        simulate_steps = request.data.get('steps')
        sec_per_step = request.data.get('sec_per_step')
        owner = request.data.get('owner')

        if not sim_code:
            return generate_response(ResultEnum.ERROR, "sim_code is required.", {})

        if not characters or not isinstance(characters, list):
            return generate_response(ResultEnum.ERROR, "characters must be a list.", {})
        
        sim_code = sim_code+"-"+owner


        # 创建实验目录
        experiment_dir = os.path.join(EXPERIMENT_STORAGE_ROOT, sim_code)
        # 检查路径是否存在
        if os.path.exists(experiment_dir):
            return generate_response(ResultEnum.ERROR, "Already have a same name simulation", {})
        else:
            os.makedirs(experiment_dir)

        # 创建环境目录
        environment_dir = os.path.join(experiment_dir, 'environment')
        os.makedirs(environment_dir, exist_ok=True)

        # 创建初始位置
        experiment_coordinates_path = os.path.join(environment_dir, '0.json')
        coordinates_data = {
            character.get('name'): {
                "maze": "the_ville",
                "x": character.get('coordinates_x', random.randint(50, 200)),
                "y": character.get('coordinates_y', random.randint(50, 200)),
            }
            for character in characters if character.get('name')  # 过滤掉没有名字的角色
        }

        # 写入数据到文件
        with open(experiment_coordinates_path, 'w') as f:
            json.dump(coordinates_data, f, indent=4)

        # 复制其他所需文件
        temp_storage_path = settings.EXPERIMENT_TEMPLATES_STORAGE_ROOT
        temp_reverie_path = os.path.join(temp_storage_path, 'reverie')
        sim_reverie_path = os.path.join(experiment_dir, 'reverie')
        MyCopyanything(temp_reverie_path, sim_reverie_path)

        # 记录人物数据到meta中
        with open(os.path.join(sim_reverie_path, "meta.json")) as json_file:
            reverie_meta = json.load(json_file)

        with open(os.path.join(sim_reverie_path, "meta.json"), "w") as outfile:
            reverie_meta["persona_names"] = [character.get('name') for character in characters]
            reverie_meta["fork_sim_code"] = sim_code
            reverie_meta["parent"] = sim_code
            reverie_meta["step"] = simulate_steps
            reverie_meta["sec_per_step"] = sec_per_step
            reverie_meta["owner"] = owner
            reverie_meta["maze_name"] = maze_name
            reverie_meta["start_date"] = start_date 
            json.dump(reverie_meta, outfile, ensure_ascii=False, indent=2)

        # 为每个角色创建文件夹和修改 scratch.json
        for character in characters:
            character_name = character.get('name')
            if not character_name:
                continue  # 如果角色名字不存在，跳过这个角色

            # 为每个角色创建目录
            persona_dir = os.path.join(experiment_dir, 'personas', character_name)
            os.makedirs(persona_dir, exist_ok=True)

            # 创建 bootstrap_memory 目录
            bootstrap_memory_dir = os.path.join(persona_dir, 'bootstrap_memory')
            os.makedirs(bootstrap_memory_dir, exist_ok=True)

            # 创建 scratch.json
            scratch_file_path = os.path.join(bootstrap_memory_dir, 'scratch.json')
            scratch_data = {
                "vision_r": 8,
                "att_bandwidth": 8,
                "retention": 8,
                "curr_time": None,
                "curr_tile": None,
                "daily_plan_req": character.get('daily_plan_req', ""),
                "name": character_name,
                "first_name": character.get('first_name', ""),
                "last_name": character.get('last_name', ""),
                "age": character.get('age', 0),
                "innate": character.get('innate', ""),
                "learned": character.get('learned', ""),
                "currently": character.get('currently', ""),
                "lifestyle": character.get('lifestyle', ""),
                "living_area": character.get('living_area', ""),
                "concept_forget": 100,
                "daily_reflection_time": 180,
                "daily_reflection_size": 5,
                "overlap_reflect_th": 4,
                "kw_strg_event_reflect_th": 10,
                "kw_strg_thought_reflect_th": 9,
                "recency_w": 1,
                "relevance_w": 1,
                "importance_w": 1,
                "recency_decay": 0.995,
                "importance_trigger_max": 150,
                "importance_trigger_curr": 150,
                "importance_ele_n": 0,
                "thought_count": 5,
                "daily_req": [],
                "f_daily_schedule": [],
                "f_daily_schedule_hourly_org": [],
                "act_address": None,
                "act_start_time": None,
                "act_duration": None,
                "act_description": None,
                "act_pronunciatio": None,
                "act_event": [character_name, None, None],
                "act_obj_description": None,
                "act_obj_pronunciatio": None,
                "act_obj_event": [None, None, None],
                "chatting_with": None,
                "chat": None,
                "chatting_with_buffer": {},
                "chatting_end_time": None,
                "act_path_set": False,
                "planned_path": []
            }

            with open(scratch_file_path, 'w') as f:
                json.dump(scratch_data, f)

            # 创建空间记忆文件
            spatial_memory_data = self.create_spatial_memory(character_name)
            spatial_memory_path = os.path.join(bootstrap_memory_dir, 'spatial_memory.json')
            with open(spatial_memory_path, 'w') as f:
                json.dump(spatial_memory_data, f)
            
            # 复制关联记忆文件
            temp_associative_memory_path = os.path.join(temp_storage_path, 'associative_memory')
            MyCopyanything(temp_associative_memory_path, os.path.join(bootstrap_memory_dir, 'associative_memory'))

        return generate_response(ResultEnum.SUCCESS, "Experiment created successfully.", {})

    def create_spatial_memory(self, character_name):
        """根据角色兴趣生成空间记忆"""
        locations = {
            "the Ville": {
                "Oak Hill College": {
                    "hallway": [],
                    "library": [
                        "library sofa",
                        "library table",
                        "bookshelf"
                    ],
                    "classroom": [
                        "blackboard",
                        "classroom podium",
                        "classroom student seating"
                    ]
                },
                "Dorm for Oak Hill College": {
                    "garden": [
                        "dorm garden"
                    ],
                    "woman's bathroom": [
                        "toilet",
                        "shower",
                        "bathroom sink"
                    ],
                    "common room": [
                        "common room sofa",
                        "pool table",
                        "common room table"
                    ],
                    "man's bathroom": [
                        "shower",
                        "bathroom sink",
                        "toilet"
                    ]
                },
                "The Willows Market and Pharmacy": {
                    "store": [
                        "grocery store shelf",
                        "behind the grocery counter",
                        "grocery store counter",
                        "pharmacy store shelf",
                        "pharmacy store counter",
                        "behind the pharmacy counter"
                    ]
                },
                "Harvey Oak Supply Store": {
                    "supply store": [
                        "supply store product shelf",
                        "behind the supply store counter",
                        "supply store counter"
                    ]
                },
                "Johnson Park": {
                    "park": [
                        "park garden"
                    ]
                },
                "The Rose and Crown Pub": {
                    "pub": [
                        "shelf",
                        "refrigerator",
                        "bar customer seating",
                        "behind the bar counter",
                        "kitchen sink",
                        "cooking area",
                        "microphone"
                    ]
                },
                "Hobbs Cafe": {
                    "cafe": [
                        "refrigerator",
                        "cafe customer seating",
                        "cooking area",
                        "kitchen sink",
                        "behind the cafe counter",
                        "piano"
                    ]
                }
            }
        }
        spatial_memory_data = {}
        for location, areas in locations['the Ville'].items():
            character_items = {}
            for area, items in areas.items():
                num_items = random.randint(0, len(items))  # 随机选择物品
                chosen_items = random.sample(items, num_items)
                character_items[area] = chosen_items
            spatial_memory_data[location] = character_items
        return spatial_memory_data
    

class ExperimentDetailView(APIView):
    """
    获取实验详细数据（人物的行为、语言等）(返回try:
            # 读取 meta.json 文件
            with open(reverie_meta_path, 'r') as f:
                meta_data = json.load(f)
                config_data_collection = meta_data
        except Exception as e:
            return generate_response(ResultEnum.ERROR, f"Error reading {config_data_collection}: {str(e)}", {})jsong格式的集合，每个人物对应一个字段)
    """
    permission_classes = [AllowAny]

    @swagger_auto_schema(
        operation_description=(
            "获取实验详细数据（人物的行为、语言等）(返回jsong格式的集合，每个人物对应一个字段)下面是示例(其中只有部分可用)：\n"
            "```json\n"
            "{\n"
            "  \"vision_r\": 8,  # 视觉分辨率\n"
            "  \"att_bandwidth\": 8,  # 注意力带宽\n"
            "  \"retention\": 8,  # 记忆保留能力\n"
            "  \"curr_time\": null,  # 当前时间\n"
            "  \"curr_tile\": null,  # 当前所在的瓷砖\n"
            "  \"daily_plan_req\": \"Klaus Mueller goes to the library at Oak Hill College early in the morning, spends his days writing, and eats at Hobbs Cafe.\",  # 日常计划\n"
            "  \"name\": \"Klaus Mueller\",  # 人物全名\n"
            "  \"first_name\": \"Klaus\",  # 名字\n"
            "  \"last_name\": \"Mueller\",  # 姓氏\n"
            "  \"age\": 20,  # 年龄\n"
            "  \"innate\": \"kind, inquisitive, passionate\",  # 天性\n"
            "  \"learned\": \"Klaus Mueller is a student at Oak Hill College studying sociology. He is passionate about social justice and loves to explore different perspectives.\",  # 学习经验\n"
            "  \"currently\": \"Klaus Mueller is writing a research paper on the effects of gentrification in low-income communities.\",  # 当前状态\n"
            "  \"lifestyle\": \"Klaus Mueller goes to bed around 11pm, awakes up around 7am, eats dinner around 5pm.\",  # 生活方式\n"
            "  \"living_area\": \"the Ville:Dorm for Oak Hill College:Klaus Mueller's room\",  # 居住区域\n"
            "  \"concept_forget\": 100,  # 概念遗忘阈值\n"
            "  \"daily_reflection_time\": 180,  # 每日反思时间（秒）\n"
            "  \"daily_reflection_size\": 5,  # 每日反思的大小\n"
            "  \"overlap_reflect_th\": 4,  # 重叠反思阈值\n"
            "  \"kw_strg_event_reflect_th\": 10,  # 关键词存储事件反思阈值\n"
            "  \"kw_strg_thought_reflect_th\": 9,  # 关键词存储思考反思阈值\n"
            "  \"recency_w\": 1,  # 最近性权重\n"
            "  \"relevance_w\": 1,  # 相关性权重\n"
            "  \"importance_w\": 1,  # 重要性权重\n"
            "  \"recency_decay\": 0.99,  # 最近性衰减系数\n"
            "  \"importance_trigger_max\": 150,  # 最大重要性触发\n"
            "  \"importance_trigger_curr\": 150,  # 当前重要性触发\n"
            "  \"importance_ele_n\": 0,  # 重要性元素数量\n"
            "  \"thought_count\": 5,  # 思考计数\n"
            "  \"daily_req\": [],  # 每日需求\n"
            "  \"f_daily_schedule\": [],  # 完整的每日时间表\n"
            "  \"f_daily_schedule_hourly_org\": [],  # 每小时组织的每日时间表\n"
            "  \"act_address\": null,  # 当前活动地址\n"
            "  \"act_start_time\": null,  # 活动开始时间\n"
            "  \"act_duration\": null,  # 活动持续时间\n"
            "  \"act_description\": null,  # 活动描述\n"
            "  \"act_pronunciatio\": null,  # 活动发音\n"
            "  \"act_event\": [\"Klaus Mueller\", null, null],  # 当前活动事件\n"
            "  \"act_obj_description\": null,  # 活动对象描述\n"
            "  \"act_obj_pronunciatio\": null,  # 活动对象发音\n"
            "  \"act_obj_event\": [null, null, null],  # 活动对象事件\n"
            "  \"chatting_with\": null,  # 当前聊天对象\n"
            "  \"chat\": null,  # 聊天内容\n"
            "  \"chatting_with_buffer\": {},  # 聊天缓冲区\n"
            "  \"chatting_end_time\": null,  # 聊天结束时间\n"
            "  \"act_path_set\": false,  # 活动路径是否设置\n"
            "  \"planned_path\": []  # 计划路径\n"
            "}\n"
            "```\n"
        ),
        manual_parameters=[
            openapi.Parameter('sim_code', openapi.IN_QUERY, description="模板实验名称: 例如：base_the_ville_isabella_maria_klaus", type=openapi.TYPE_STRING)
        ],
        responses={
            ResultEnum.SUCCESS: openapi.Response(description="返回实验详细数据"),
            ResultEnum.ERROR: openapi.Response(description="参数验证失败/Experiment not found."),
        }
    )
    def get(self, request):
        """
        获取实验详细数据
        """
        sim_code = request.GET.get('sim_code')
        if not sim_code:
            return generate_response(ResultEnum.ERROR, "sim_code is required.", {})

        # 目标实验路径
        experiment_dir_personas = os.path.join(EXPERIMENT_STORAGE_ROOT, sim_code, 'personas')
        experiment_dir_reverie = os.path.join(EXPERIMENT_STORAGE_ROOT, sim_code, 'reverie')

        # 检查路径是否存在
        if not os.path.exists(experiment_dir_personas) or not os.path.exists(experiment_dir_reverie):
            return generate_response(ResultEnum.ERROR, "Experiment not found.", {})

        # 存储所有 bootstrap_memory/scratch.json 文件内容的集合
        scratch_data_collection = []

        # 遍历子目录
        for subdir, dirs, files in os.walk(experiment_dir_personas):
            for file in files:
                # 如果是 bootstrap_memory/scratch.json 文件
                if file == 'scratch.json':
                    scratch_file_path = os.path.join(subdir, file)
                    try:
                        # 读取 scratch.json 文件
                        with open(scratch_file_path, 'r') as f:
                            scratch_data = json.load(f)
                            scratch_data_collection.append(scratch_data)
                    except Exception as e:
                        return generate_response(ResultEnum.ERROR, f"Error reading {scratch_file_path}: {str(e)}", {})
        # 储存reverie/meta.json的实验配置信息
        config_data_collection = {}
        reverie_meta_path = os.path.join(experiment_dir_reverie,"meta.json")
        try:
            # 读取 meta.json 文件
            with open(reverie_meta_path, 'r') as f:
                meta_data = json.load(f)
                config_data_collection = meta_data
        except Exception as e:
            return generate_response(ResultEnum.ERROR, f"Error reading {reverie_meta_path}: {str(e)}", {})

        # 返回集合数据
        return generate_response(ResultEnum.SUCCESS, "Scratch data retrieved successfully.", {
            "scratch_data_collection": scratch_data_collection,
            "config" : config_data_collection
        })


import os
import json
import logging
import asyncio
import threading
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
import aiofiles  # 确保安装 aiofiles

class ExperimentStartView(APIView):
    """
    启动实验并执行外部 Bash 脚本，并通过 WebSocket 发送输出
    """
    permission_classes = []

    @swagger_auto_schema(
        operation_description="启动实验并执行外部脚本(并通过 WebSocket 发送输出)",
        manual_parameters=[
            openapi.Parameter(
                'sim_code',
                openapi.IN_QUERY,
                description="模板实验名称: 例如：base_the_ville_isabella_maria_klaus",
                type=openapi.TYPE_STRING,
                required=True
            ),
            openapi.Parameter(
                'target',
                openapi.IN_QUERY,
                description="目标实验名称",
                type=openapi.TYPE_STRING,
                required=True  
            ),
            openapi.Parameter(
                'steps',
                openapi.IN_QUERY,
                description="实验步骤数",
                type=openapi.TYPE_INTEGER,
                required=True 
            ),
            openapi.Parameter(
                'owner',
                openapi.IN_QUERY,
                description="实验所属者",
                type=openapi.TYPE_STRING,
                required=True 
            ),
        ],
        responses={
            ResultEnum.SUCCESS: openapi.Response(description="实验启动成功"),
            ResultEnum.ERROR: openapi.Response(description="参数验证失败"),
            ResultEnum.ERROR: openapi.Response(description="执行脚本不存在")
        }
    )
    def post(self, request):
        """启动实验并执行 Bash 脚本"""
        # 获取参数
        sim_code = request.GET.get('sim_code')
        target = request.GET.get('target')
        simulate_steps = request.GET.get('steps', 0)
        owner = request.GET.get('owner')
        target = target+"-"+owner # 用用户名字个性化

        # 参数验证
        if not sim_code or not target:
            return generate_response(ResultEnum.ERROR, "sim_code and target are required.", {})
        if sim_code == target:
            return generate_response(ResultEnum.ERROR, "sim_code and target are the same.", {})

        try:
            simulate_steps = int(simulate_steps)
        except ValueError:
            return generate_response(ResultEnum.ERROR, "steps must be an integer.", {})

        # 获取脚本路径
        backend_script_path = os.path.join(settings.ROOT_DIR, "run_backend_automatic.sh")
        if not os.path.exists(backend_script_path):
            return generate_response(ResultEnum.ERROR, "Bash script not found.", {})

        # 准备 Bash 脚本的参数
        bash_command = [
            'bash', backend_script_path,
            '--origin', sim_code, 
            '--target', target, 
            '--steps', str(simulate_steps),
            '--ui', 'false',
            '--port', '8000',
            '--owner', owner
        ]

        # 在脚本执行前创建目标文件夹，避免由于异步导致访问文件失败
        sim_folder = os.path.join(EXPERIMENT_STORAGE_ROOT, sim_code)
        target_folder = os.path.join(EXPERIMENT_STORAGE_ROOT, target)
        # 检查路径是否存在
        if os.path.exists(target_folder):
            return generate_response(ResultEnum.ERROR, "Already have a same name experiment", {})
        
        MyCopyanything(sim_folder, target_folder)

        # 使用线程启动异步事件循环
        thread = threading.Thread(target=self.run_async_task, args=(target, bash_command))
        thread.start()

        return generate_response(ResultEnum.SUCCESS, "Experiment started successfully.", {
            "webSocket": f"ws://{request.get_host()}/ws/experiment/{target}/"
        })

    def run_async_task(self, target, bash_command):
        """创建新的事件循环并运行异步任务"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self.async_run_process(target, bash_command))

    async def async_run_process(self, target, bash_command):
        """使用 asyncio 启动 Bash 进程并监听输出"""
        try:
            process = await asyncio.create_subprocess_exec(
                *bash_command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            # 更新实验元数据
            print(f"Experiment PID: {process.pid}")
            await self.update_meta_status(target, process.pid, ExperimentStatus.RUNNING)


            # 创建监听 stdout 和 stderr 的任务
            stdout_task = asyncio.create_task(self.read_stream(target, process.stdout))
            stderr_task = asyncio.create_task(self.read_stream(target, process.stderr, is_error=True))

            await asyncio.gather(stdout_task, stderr_task)
            await process.wait()

            # 更新实验结束状态
            await self.update_meta_status(target, None, ExperimentStatus.FINISHED)

            # 发送实验结束消息
            await self.send_websocket_message(target, "Experimental simulation finished")

        except Exception as e:
            logging.error(f"Error executing bash script: {e}")
            await self.send_websocket_message(target, f"Error: {str(e)}")
            await self.update_meta_status(target, None, ExperimentStatus.NOT_STARTED)  # 在出错时重置状态

    async def update_meta_status(self, target, pid, status):
        """更新实验的元数据文件"""
        target_reverie_meta_path = os.path.join(EXPERIMENT_STORAGE_ROOT, target, "reverie", "meta.json")
        try:
            # 使用 aiofiles 读取 meta.json 文件
            async with aiofiles.open(target_reverie_meta_path, 'r') as f:
                meta_data = json.loads(await f.read())

            # 更新 meta 数据
            if pid is not None:
                meta_data["pid"] = pid
            meta_data["status"] = status.value
            print(meta_data["pid"], "是当前存入的pid")

            # 写回更新后的数据
            async with aiofiles.open(target_reverie_meta_path, 'w') as f:
                await f.write(json.dumps(meta_data, ensure_ascii=False, indent=2))

        except Exception as e:
            logging.error(f"Error reading or updating {target_reverie_meta_path}: {str(e)}")
            await self.send_websocket_message(target, f"Error updating status: {str(e)}")

    async def read_stream(self, target, stream, is_error=False):
        """异步读取输出流并通过 WebSocket 发送"""
        while not stream.at_eof():
            line = await stream.readline()
            if line:
                message = line.strip()
                if isinstance(message, bytes):
                    message = message.decode()
                if is_error:
                    message = f"ERROR: {message}"
                await self.send_websocket_message(target, message)

    async def send_websocket_message(self, target, message):
        """通过 WebSocket 发送消息"""
        try:
            channel_layer = get_channel_layer()
            await channel_layer.group_send(
                f"experiment_{target}",  # 使用唯一的组名称
                {
                    "type": "send_message",
                    "message": message,
                }
            )
        except Exception as e:
            logging.error(f"WebSocket发送失败: {str(e)}")


class ExperimentStatusView(APIView):
    """
    查询实验状态（是否跑完流程），返回 not started / running / finished
    """
    permission_classes = [AllowAny]

    @swagger_auto_schema(
        operation_description="查询实验状态 not started / running / finished(通过cache存储start创建的脚本PID)",
        manual_parameters=[
            openapi.Parameter('sim_code', openapi.IN_QUERY, description="模板实验名称: 例如：base_the_ville_isabella_maria_klaus", type=openapi.TYPE_STRING)
        ],
        responses={
            ResultEnum.SUCCESS: openapi.Response(description="返回实验状态"),
            ResultEnum.ERROR: openapi.Response(description="参数验证失败"),
        }
    )
    def get(self, request):
        """查询实验状态"""
        sim_code = request.GET.get('sim_code')
        if not sim_code:
            return generate_response(ResultEnum.ERROR, "sim_code is required.", {})

        target_reverie_meta_path = os.path.join(EXPERIMENT_STORAGE_ROOT, sim_code, "reverie", "meta.json")
        try:
            # 读取 meta.json 文件
            with open(target_reverie_meta_path, 'r') as f:
                meta_data = json.load(f)

            status = meta_data.get("status", ExperimentStatus.NOT_STARTED.value)
            current_step = meta_data.get("current_step", 0)
            total_step = meta_data.get("step", 0)

            if status == ExperimentStatus.NOT_STARTED.value:
                return generate_response(ResultEnum.SUCCESS, "成功获取实验状态", {
                    "status": status,
                    "current_step": current_step,
                    "total_step": total_step
                })

            # 检查进程是否仍在运行
            elif status == ExperimentStatus.RUNNING.value and self.is_process_running(meta_data.get("pid")):
                return generate_response(ResultEnum.SUCCESS, "成功获取实验状态", {
                    "status": ExperimentStatus.RUNNING.value,
                    "current_step": current_step,
                    "total_step": total_step
                })

            # 如果进程不再运行，则返回 finished 状态
            meta_data["status"] = ExperimentStatus.FINISHED.value # 确保当前状态正确
            with open(target_reverie_meta_path, 'w') as f:
                json.dump(meta_data, f, ensure_ascii=False, indent=2)
            return generate_response(ResultEnum.SUCCESS, "成功获取实验状态", {
                "status": ExperimentStatus.FINISHED.value,
                "current_step": current_step,
                "total_step": total_step
            })

        except FileNotFoundError:
            return generate_response(ResultEnum.ERROR, f"Meta file not found at {target_reverie_meta_path}.", {})
        except json.JSONDecodeError:
            return generate_response(ResultEnum.ERROR, "Error decoding meta.json.", {})
        except Exception as e:
            logging.error(f"Error reading or updating {target_reverie_meta_path}: {str(e)}")
            return generate_response(ResultEnum.ERROR, f"Unexpected error: {str(e)}", {})

    def is_process_running(self, pid):
        """检查指定的进程 ID 是否仍在运行"""
        try:
            os.kill(pid, 0)  # 发送信号 0 检查进程是否存在
            return True
        except ProcessLookupError:
            return False
        except Exception:
            return False

class ExperimentStopView(APIView):
    """
    终止实验
    """
    permission_classes = [AllowAny]

    @swagger_auto_schema(
        operation_description="终止实验（通过cache储存sim_code对应的进程ID，通过进程PID终止脚本）",
        manual_parameters=[
            openapi.Parameter('sim_code', openapi.IN_QUERY, description="模板实验名称: 例如：base_the_ville_isabella_maria_klaus", type=openapi.TYPE_STRING)
        ],
        responses={
            ResultEnum.SUCCESS: openapi.Response(description="实验终止成功"),
            ResultEnum.ERROR: openapi.Response(description="参数验证失败"),
            ResultEnum.ERROR: openapi.Response(description="未找到实验"),
            ResultEnum.ERROR: openapi.Response(description="服务器错误"),
        }
    )
    def post(self, request):
        """终止实验"""
        sim_code = request.GET.get('sim_code')
        if not sim_code:
            return generate_response(ResultEnum.ERROR, "sim_code is required.", {})

        target_reverie_meta_path = os.path.join(EXPERIMENT_STORAGE_ROOT, sim_code, "reverie", "meta.json")
        try:
            # 读取 meta.json 文件
            with open(target_reverie_meta_path, 'r') as f:
                meta_data = json.load(f)

            pid = meta_data.get("pid")
            status = meta_data.get("status")
            if status == ExperimentStatus.NOT_STARTED.value:
                return generate_response(ResultEnum.ERROR, "No running experiment found with the given sim_code.", {})

            # 检查进程是否仍在运行
            elif status != ExperimentStatus.RUNNING.value or not self.is_process_running(pid):
                return generate_response(ResultEnum.ERROR, "The process is not running.", {})
            
            # 检查进程是否仍在运行
            elif status == ExperimentStatus.FINISHED.value:
                return generate_response(ResultEnum.ERROR, "The experiment has finished.", {})

            # 尝试停止进程
            print("当前停止的实验是：",pid)
            self.terminate_process_and_children(pid)  # 终止进程及其子进程
            # 如果进程不再运行，则返回 finished 状态
            meta_data["status"] = ExperimentStatus.FINISHED.value # 确保当前状态正确
            with open(target_reverie_meta_path, 'w') as f:
                json.dump(meta_data, f, ensure_ascii=False, indent=2)
            return generate_response(ResultEnum.SUCCESS, "Experiment stopped successfully.", {})
        
        except FileNotFoundError:
            return generate_response(ResultEnum.ERROR, f"Meta file not found at {target_reverie_meta_path}.", {})
        except json.JSONDecodeError:
            return generate_response(ResultEnum.ERROR, "Error decoding meta.json.", {})
        except ProcessLookupError:
            return generate_response(ResultEnum.ERROR, "Process not found.", {})
        except Exception as e:
            logging.error(f"Error stopping the process: {str(e)}")
            return generate_response(ResultEnum.ERROR, f"Unexpected error: {str(e)}", {})

    def is_process_running(self, pid):
        """检查指定的进程 ID 是否仍在运行"""
        try:
            os.kill(pid, 0)  # 发送信号 0 检查进程是否存在
            return True
        except ProcessLookupError:
            return False
        except Exception:
            return False
        
    def terminate_process_and_children(self, pid):
        """终止进程及其子进程"""
        try:
            parent = psutil.Process(pid)
            for child in parent.children(recursive=True):  # 获取所有子进程
                child.kill()  # 强制终止子进程
            parent.kill()  # 然后终止父进程
        except ProcessLookupError:
            logging.error("Process not found when trying to terminate.")
        except Exception as e:
            logging.error(f"Error terminating process and children: {e}")


class ExperimentDeleteView(APIView):
    """
    删除指定实验
    """
    permission_classes = [AllowAny]

    @swagger_auto_schema(
        operation_description="根据实验名称删除指定实验",
        manual_parameters=[
            openapi.Parameter(
                'sim_code',
                openapi.IN_QUERY,
                description="模板实验名称: 例如：base_the_ville_isabella_maria_klaus，指定要删除的实验",
                type=openapi.TYPE_STRING,
                required=True
            )
        ],
        responses={
            ResultEnum.SUCCESS: openapi.Response(description="实验删除成功"),
            ResultEnum.ERROR: openapi.Response(description="未找到指定实验"),
            ResultEnum.ERROR: openapi.Response(description="错误信息"),
        }
    )
    def delete(self, request):
        """ 删除实验 """
        sim_code = request.query_params.get('sim_code')

        if not sim_code:
            return generate_response(ResultEnum.ERROR, "sim_code is required.", {})

        experiment_dir = os.path.join(EXPERIMENT_STORAGE_ROOT, sim_code)

        if not os.path.exists(experiment_dir):
            return generate_response(ResultEnum.ERROR, "Experiment not found.", {})

        # 删除实验目录
        try:
            shutil.rmtree(experiment_dir)  # 删除实验目录
            return generate_response(ResultEnum.SUCCESS, "Experiment deleted successfully.", {})
        except OSError as e:
            return generate_response(ResultEnum.ERROR, f"Error deleting experiment: {str(e)}", {})
        

class ExperimentParentCheckView(APIView):
    """
    查询当前实验是模板还是由模板创建的模拟历史
    """
    permission_classes = [AllowAny]

    @swagger_auto_schema(
        operation_description="根据实验名称检查实验的类型",
        manual_parameters=[
            openapi.Parameter(
                'sim_code',
                openapi.IN_QUERY,
                description="实验名称: 例如：base_the_ville_isabella_maria_klaus，指定要检查的实验",
                type=openapi.TYPE_STRING,
                required=True
            )
        ],
        responses={
            ResultEnum.SUCCESS: openapi.Response(description="实验类型查询成功"),
            ResultEnum.ERROR: openapi.Response(description="未找到指定实验"),
            ResultEnum.ERROR: openapi.Response(description="错误信息"),
        }
    )
    def get(self, request):
        """ 查询实验类型 """
        sim_code = request.query_params.get('sim_code')

        if not sim_code:
            return generate_response(ResultEnum.ERROR, "sim_code is required.", {})

        experiment_dir = os.path.join(EXPERIMENT_STORAGE_ROOT, sim_code)

        if not os.path.exists(experiment_dir):
            return generate_response(ResultEnum.ERROR, "Experiment not found.", {})

        # 检查配置文件并返回相关信息
        reverie_meta_path = os.path.join(experiment_dir, "reverie/meta.json")
        try:
            # 读取 meta.json 文件
            with open(reverie_meta_path, 'r') as f:
                meta_data = json.load(f)
                if meta_data.get("parent") == sim_code:
                    return generate_response(ResultEnum.SUCCESS, "该目录是实验模板", {"parent": meta_data["parent"],"isTemplate":True})
                else:
                    return generate_response(ResultEnum.SUCCESS, "该目录不是实验模板，是模拟历史", {"parent": meta_data["parent"],"isTemplate":False})
        except Exception as e:
            return generate_response(ResultEnum.ERROR, f"Error reading {reverie_meta_path}: {str(e)}", {})
        


class TemplateExperimentView(APIView):
    """
    查询实验是否为模板实验，并返回其子实验的列表
    """
    permission_classes = [AllowAny]

    def _get_experiments(self):
        """ 获取实验列表 """
        try:
            return os.listdir(EXPERIMENT_STORAGE_ROOT)
        except FileNotFoundError:
            return generate_response(ResultEnum.ERROR, "实验存储目录不存在", None)
        except PermissionError:
            return generate_response(ResultEnum.ERROR, "目录访问权限不足", None)

    @swagger_auto_schema(
        operation_description="查询实验是否为模板实验，并返回其子实验的列表",
        manual_parameters=[
            openapi.Parameter('sim_code', openapi.IN_QUERY, description="模板实验名称，例如：base_the_ville_isabella_maria_klaus", type=openapi.TYPE_STRING)
        ],
        responses={
            ResultEnum.SUCCESS: openapi.Response(
                description="成功获取子实验列表",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'code': openapi.Schema(type=openapi.TYPE_INTEGER),
                        'message': openapi.Schema(type=openapi.TYPE_STRING),
                        'data': openapi.Schema(
                            type=openapi.TYPE_OBJECT,
                            properties={
                                'sub_experiments': openapi.Schema(
                                    type=openapi.TYPE_ARRAY,
                                    items=openapi.Items(type=openapi.TYPE_OBJECT, properties={
                                        'name': openapi.Schema(type=openapi.TYPE_STRING),
                                        'type': openapi.Schema(type=openapi.TYPE_STRING),
                                        'status': openapi.Schema(type=openapi.TYPE_STRING),
                                        'current_step': openapi.Schema(type=openapi.TYPE_INTEGER),
                                        'isTemplate': openapi.Schema(type=openapi.TYPE_BOOLEAN),
                                    })
                                ),
                                'is_template': openapi.Schema(type=openapi.TYPE_BOOLEAN)
                            }
                        ),
                    }
                )
            ),
            ResultEnum.ERROR: openapi.Response(
                description="错误信息",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'code': openapi.Schema(type=openapi.TYPE_INTEGER),
                        'message': openapi.Schema(type=openapi.TYPE_STRING)
                    }
                )
            )
        }
    )
    def get(self, request, *args, **kwargs):
        """ 统一入口处理 GET 请求 """
        sim_code = request.query_params.get('sim_code', '')  # 获取实验名称参数
        if not sim_code:
            return generate_response(ResultEnum.ERROR, "实验名称未提供", None)

        # 构建目标实验的 meta.json 路径
        experiment_reverie_meta_path = os.path.join(EXPERIMENT_STORAGE_ROOT, sim_code, "reverie/meta.json")

        # 检查目标实验是否存在并读取其元数据
        try:
            with open(experiment_reverie_meta_path, 'r') as f:
                meta_data = json.load(f)
                if "parent" not in meta_data:
                    return generate_response(ResultEnum.SUCCESS, "This experiment is not a template experiment", {"is_template": False, "sub_experiments": []})

        except FileNotFoundError:
            return generate_response(ResultEnum.ERROR, "The target experiment does not exist", None)

        # 获取实验列表
        experiments = self._get_experiments()

        if isinstance(experiments, Response):  # 检查是否返回了错误响应
            return experiments

        sub_experiments = []

        # 遍历实验列表，查找子实验
        for exp in experiments:
            experiment_dir = os.path.join(EXPERIMENT_STORAGE_ROOT, exp)
            reverie_meta_path = os.path.join(experiment_dir, "reverie/meta.json")

            try:
                with open(reverie_meta_path, 'r') as f:
                    meta_data = json.load(f)
                    # 检查子实验的 parent 字段是否等于目标实验名称
                    if meta_data.get("parent") == sim_code and exp != sim_code:
                        sub_experiments.append({
                            "name": exp,
                            "type": "public" if exp in PUBLIC_EXPERIMENT_WHITELIST else "private",
                            "status": meta_data.get("status"),
                            "current_step": meta_data.get("current_step"),
                            "isTemplate": False,
                        })

            except FileNotFoundError:
                continue  # 跳过该实验

        return generate_response(
            ResultEnum.SUCCESS,
            "This experiment is a template experiment",
            {
                "is_template": True,
                "sub_experiments": sub_experiments
            }
        )