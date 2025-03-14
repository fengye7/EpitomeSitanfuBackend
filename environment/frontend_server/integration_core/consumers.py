# consumers.py

from channels.generic.websocket import AsyncWebsocketConsumer
import json

class ExperimentConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.sim_code = self.scope['url_route']['kwargs']['sim_code']
        self.group_name = f"experiment_{self.sim_code}"
        
        # 将连接加入固定组
        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name
        )
        # print("尝试websocket连接")
        # 接受WebSocket连接
        await self.accept()
        # await self.send(text_data=json.dumps({
        #     'message': 'Connected to the experiment group.'
        # }))

    async def disconnect(self, close_code):
        # print("尝试websocket断开")
        await self.channel_layer.group_discard(
            self.group_name,
            self.channel_name
        )

    async def send_message(self, event):
        message = event['message']
        await self.send(text_data=json.dumps({
            'message': message
        }))

    async def receive(self, text_data):
        """处理从WebSocket客户端接收到的消息"""
        data = json.loads(text_data)
        message = data.get('message', '')

        # 打印接收到的消息
        print(f"Received message: {message}")

        # 可以选择将接收到的消息发送回去或进行其他处理
        await self.send(text_data=json.dumps({
            'message': f"Message received: {message}"
        }))