<template>
  <div class="empty-state">
    <div class="illustration">
      <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 96 96" aria-hidden="true">
        <path fill="#64748B" d="M48 16a32 32 0 1 0 0 64 32 32 0 0 0 0-64Zm0 8a24 24 0 0 1 24 24c0 6.1-3.9 11.4-9.6 14.4l-14-14a2 2 0 0 0-2.8 0l-14 14C27.9 59.4 24 54.1 24 48A24 24 0 0 1 48 24Z"/>
        <path fill="#94A3B8" d="m62.4 62.4-14-14a2 2 0 0 0-2.8 0l-14 14C27.9 59.4 24 54.1 24 48a24 24 0 1 1 48 0c0 6.1-3.9 11.4-9.6 14.4Z"/>
        <circle cx="48" cy="48" r="6" fill="#E2E8F0"/>
      </svg>
    </div>
    
    <div class="content">
      <h3 class="title">无选中实验</h3>
      <p class="description">
        请从左侧列表选择实验，或创建新的仿真实验 
      </p>
    </div>

    <div class="websocket-test">
      <input v-model="message" placeholder="输入消息" />
      <button @click="sendMessage">发送消息</button>
      <button @click="clearResponses">清理响应</button>
      <div class="response" v-if="responses.length">
        <strong>响应:</strong>
        <ul>
          <li v-for="(resp, index) in responses" :key="index">{{ resp }}</li>
        </ul>
      </div>
      <div v-if="!isConnected" class="connection-status">连接已断开，尝试重新连接...</div>
    </div>
    <iframe src="https://tiled-map-editor-url" width="800" height="600"></iframe>
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue';

const message = ref('');
const responses = ref([]); // 用数组来存储增量响应
let socket = null;
const isConnected = ref(false); // 连接状态
let reconnectInterval = null;

const connectWebSocket = () => {
  socket = new WebSocket("ws://localhost:8000/ws/experiment/target/");

  // 监听 WebSocket 消息
  socket.onmessage = (event) => {
    const data = JSON.parse(event.data);
    const responseMessage = data.output || data.message; // 处理输出
    responses.value.push(responseMessage); // 增量添加消息
  };

  // 监听错误
  socket.onerror = (error) => {
    console.error('WebSocket error:', error);
  };

  socket.onopen = function() {
    console.log("WebSocket connection established.");
    isConnected.value = true; // 更新连接状态
    if (reconnectInterval) {
      clearInterval(reconnectInterval); // 清除重连定时器
    }
  };

  socket.onclose = function() {
    console.log("WebSocket connection closed.");
    isConnected.value = false; // 更新连接状态
    // 开始重连
    reconnectInterval = setInterval(() => {
      console.log("尝试重新连接...");
      connectWebSocket(); // 尝试重新连接
    }, 3000); // 每3秒重连一次
  };
};

onMounted(() => {
  connectWebSocket(); // 初始化 WebSocket 连接
});

const sendMessage = () => {
  if (message.value && isConnected.value) {
    socket.send(JSON.stringify({ message: message.value }));
    message.value = ''; // 清空输入框
  }
};

// 清理响应功能
const clearResponses = () => {
  responses.value = []; // 清空响应数组
};

onBeforeUnmount(() => {
  // 关闭 WebSocket 连接
  if (socket) {
    socket.close();
  }
});
</script>

<style scoped>
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  padding: 2rem;
  text-align: center;
  background: rgba(255, 255, 255, 0.03);
  border-radius: 12px;
  border: 1px dashed rgba(255, 255, 255, 0.1);
  margin: 16px;
}

.websocket-test {
  margin-top: 2rem;
}

input {
  padding: 0.5rem;
  margin-right: 0.5rem;
}

button {
  padding: 0.5rem 1rem;
  background-color: #64748B;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  margin-right: 0.5rem; /* 增加按钮之间的间距 */
}

button:hover {
  background-color: #4B5563;
}

.response {
  margin-top: 1rem;
  background-color: black; /* 设置黑色背景 */
  color: #94A3B8; /* 文本颜色 */
  padding: 1rem; /* 内边距 */
  border-radius: 8px; /* 圆角 */
  max-height: 200px; /* 最大高度 */
  overflow-y: auto; /* 超出部分生成滚动条 */
  text-align: left; /* 左对齐 */
}

.connection-status {
  margin-top: 1rem;
  color: red; /* 警告颜色 */
}
</style>