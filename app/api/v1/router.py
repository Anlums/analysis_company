from fastapi import APIRouter

api_router = APIRouter()

# 各模块路由按技术架构文档第五章挂载到这里：
#   tasks      任务提交 / 状态 / 分层结果
#   documents  文档上传 / 解析触发
#   evidence   按证据锚点取原文片段
#   events     SSE 执行事件流
