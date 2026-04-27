"""
知识检索服务模块

功能介绍：
-----------
本模块封装了阿里云百炼（Bailian）知识库检索 API，
用于从已索引的校园知识文档中检索与用户问题相关的文本块。

主要组件：
- KnowledgeRetriever: 百炼检索客户端封装类
- get_retriever(): 返回模块级单例实例

检索流程：
1. 构建 RetrieveRequest（含 dense/sparse 检索、rerank 重排）
2. 调用百炼 retrieve_with_options API
3. 解析响应中的 Nodes/Chunks，拼接为文本块
4. 返回供下游 LLM 使用的上下文文本

降级处理：
- API 异常或返回空结果时，返回 "未在知识库中找到相关信息。"
"""
from __future__ import annotations

import json
from typing import Any

from alibabacloud_bailian20231229 import models as bailian_models
from alibabacloud_bailian20231229.client import Client as BailianClient
from alibabacloud_tea_openapi import models as open_api_models
from alibabacloud_tea_util import models as util_models

from app.config import settings
from app.utils.logger import logger

# 小于此长度的文本块被认为太短，不适合作为上下文。
_MIN_CHUNK_LENGTH = 5


class KnowledgeRetriever:
    """从百炼知识库索引中检索相关文本块。"""

    def __init__(
        self,
        workspace_id: str | None = None,
        index_id: str | None = None,
    ):
        self.workspace_id = workspace_id or settings.BAILIAN_WORKSPACE_ID
        self.index_id = index_id or settings.BAILIAN_INDEX_ID
        self._client: BailianClient | None = None

    @property
    def client(self) -> BailianClient:
        if self._client is None:
            config = open_api_models.Config(
                access_key_id=settings.ALIBABA_CLOUD_ACCESS_KEY_ID,
                access_key_secret=settings.ALIBABA_CLOUD_ACCESS_KEY_SECRET,
            )
            config.endpoint = settings.BAILIAN_ENDPOINT
            self._client = BailianClient(config)
        return self._client

    def search(self, query: str) -> str:
        """搜索知识库并返回拼接的文本块。

        参数：
            query: 用户的自然语言问题。
        返回：
            拼接的文本块字符串。
        """
        try:
            logger.info("Knowledge retriever search start: query_len={}", len(query))
            request = bailian_models.RetrieveRequest(
                index_id=self.index_id,
                query=query,
                dense_similarity_top_k=50,
                sparse_similarity_top_k=50,
                enable_reranking=True,
                rerank=[
                    bailian_models.RetrieveRequestRerank(
                        model_name="qwen3-rerank"
                    )
                ],
                rerank_min_score=0.01,
                rerank_top_n=5,
            )
            runtime = util_models.RuntimeOptions()

            resp = self.client.retrieve_with_options(
                self.workspace_id, request, {}, runtime,
            )

            # 正常化响应体为一个普通字典
            if hasattr(resp.body, "to_map"):
                raw_data = resp.body.to_map()
            else:
                raw_data = json.loads(
                    json.dumps(resp.body, default=lambda o: o.__dict__)
                )

            # 检查响应成功与否
            success = raw_data.get("Success") or (
                raw_data.get("Code") == "Success"
            )
            if not success:
                # 记录错误并返回通用消息
                error_msg = (
                    raw_data.get("Message")
                    or raw_data.get("message")
                    or "未知错误"
                )
                logger.error("Bailian search API error: {}", error_msg)
                return "未在知识库中找到相关信息。"

            # 提取 Nodes 数据
            data = raw_data.get("Data", {})
            nodes = data.get("Nodes", [])

            content_list: list[str] = []
            if nodes:
                # 优先处理 Nodes 结构
                for node in nodes:
                    text = node.get("Text", "").strip()
                    if text and len(text) > _MIN_CHUNK_LENGTH:
                        content_list.append(text)
            else:
                # 回退到旧逻辑（防止 API 结构差异）
                chunks = _extract_chunks(raw_data)
                for chunk in chunks:
                    content = (
                        chunk.get("content")
                        or chunk.get("text")
                        or chunk.get("page_content")
                        or str(chunk)
                    )
                    if (
                        content
                        and len(str(content).strip()) > _MIN_CHUNK_LENGTH
                    ):
                        content_list.append(str(content))

            if not content_list:
                logger.info("Knowledge retriever search empty result")
                return "未在知识库中找到相关信息。"

            logger.info("Knowledge retriever search success: chunks={}", len(content_list))
            return "\n\n".join(content_list)

        except Exception as e:
            logger.exception("Knowledge retriever search exception")
            return "未在知识库中找到相关信息。"


def _extract_chunks(raw_data: dict[str, Any]) -> list[dict]:
    """遍历API响应并定位文本块列表。"""
    data = raw_data.get("data", {})

    chunks: list[dict] = []
    if isinstance(data, dict):
        if "chunks" in data:
            chunks = data["chunks"]
        elif "result" in data:
            chunks = data["result"]
    elif isinstance(data, list):
        chunks = data

    # 备用：尝试根级键
    if not chunks and isinstance(raw_data, dict):
        if "chunks" in raw_data:
            chunks = raw_data["chunks"]

    return chunks


# 模块级单例（懒加载 – 客户端在第一次调用时创建）
_retriever: KnowledgeRetriever | None = None


def get_retriever() -> KnowledgeRetriever:
    """返回模块级检索实例。"""
    global _retriever
    if _retriever is None:
        _retriever = KnowledgeRetriever()
    return _retriever
