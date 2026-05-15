"""
语义高亮服务
使用 semantic-highlight-bilingual-v1 模型对检索到的文档块进行语义高亮处理
"""
import logging
import os
from typing import Dict, List, Optional
import threading

logger = logging.getLogger(__name__)


class SemanticHighlightService:
    """语义高亮服务，用于提取与查询最相关的句子"""
    
    def __init__(
        self,
        model_path: str = "/home/songbinbin/Proj/hf_models/semantic-highlight-bilingual-v1",
        enabled: bool = True,
        threshold: float = 0.5
    ):
        """
        初始化语义高亮服务
        
        Args:
            model_path: 模型路径
            enabled: 是否启用语义高亮（默认 True）
            threshold: 高亮阈值（默认 0.5）
        """
        self.model_path = model_path
        self.enabled = enabled
        self.threshold = threshold
        self.model = None
        self._lock = threading.Lock()  # 用于线程安全的模型加载
    
    def _load_model(self):
        """懒加载模型（线程安全）"""
        if self.model is not None:
            return
        
        with self._lock:
            # 双重检查，避免多线程重复加载
            if self.model is not None:
                return
            
            try:
                if not self.enabled:
                    logger.info("语义高亮功能已禁用")
                    return
                
                if not os.path.exists(self.model_path):
                    logger.warning(f"模型路径不存在: {self.model_path}，语义高亮功能将不可用")
                    self.enabled = False
                    return
                
                logger.info(f"正在加载语义高亮模型: {self.model_path}")
                from transformers import AutoModel
                
                self.model = AutoModel.from_pretrained(
                    self.model_path,
                    trust_remote_code=True
                )
                
                # 设置为评估模式
                self.model.eval()
                
                logger.info("语义高亮模型加载成功")
            except Exception as e:
                logger.error(f"加载语义高亮模型失败: {e}", exc_info=True)
                self.model = None
                self.enabled = False
    
    def highlight(
        self,
        query: str,
        context: str,
        threshold: Optional[float] = None
    ) -> Dict:
        """
        对文档内容进行语义高亮处理
        
        Args:
            query: 查询文本
            context: 文档内容
            threshold: 高亮阈值（可选，默认使用初始化时的阈值）
        
        Returns:
            包含高亮结果的字典：
            {
                "highlighted_sentences": List[str],  # 高亮句子列表
                "sentence_probabilities": List[float],  # 句子概率分数（可选）
                "compression_rate": float  # 压缩率（保留的文本比例）
            }
        """
        logger.info(f"语义高亮处理: enabled={self.enabled}, model_path={self.model_path}")
        
        # 如果未启用或模型未加载，返回原始内容
        if not self.enabled:
            logger.info("语义高亮功能未启用，返回降级结果")
            return self._fallback_result(context)
        
        # 懒加载模型
        try:
            self._load_model()
        except Exception as e:
            logger.error(f"模型加载异常: {e}", exc_info=True)
            return self._fallback_result(context)
        
        if self.model is None:
            logger.warning("语义高亮模型未加载，返回降级结果")
            return self._fallback_result(context)
        
        # 检查输入
        if not query or not context:
            return self._fallback_result(context)
        
        try:
            # 使用模型进行高亮处理
            threshold = threshold or self.threshold
            
            result = self.model.process(
                question=query,
                context=context,
                threshold=threshold,
                return_sentence_metrics=True
            )
            
            # 提取高亮句子
            highlighted_sentences = result.get("highlighted_sentences", [])
            sentence_probabilities = result.get("sentence_probabilities", [])
            compression_rate = result.get("compression_rate", 0.0)
            
            logger.debug(
                f"语义高亮完成: 查询长度={len(query)}, "
                f"上下文长度={len(context)}, "
                f"高亮句子数={len(highlighted_sentences)}, "
                f"压缩率={compression_rate:.2%}"
            )
            
            return {
                "highlighted_sentences": highlighted_sentences,
                "sentence_probabilities": sentence_probabilities,
                "compression_rate": compression_rate
            }
        
        except Exception as e:
            logger.error(f"语义高亮处理失败: {e}", exc_info=True)
            return self._fallback_result(context)
    
    def _fallback_result(self, context: str) -> Dict:
        """
        降级处理：返回原始内容
        
        Args:
            context: 原始文档内容
        
        Returns:
            降级结果字典
        """
        return {
            "highlighted_sentences": [],
            "sentence_probabilities": [],
            "compression_rate": 0.0
        }
    
    def is_available(self) -> bool:
        """检查语义高亮功能是否可用"""
        if not self.enabled:
            return False
        
        try:
            self._load_model()
            return self.model is not None
        except Exception:
            return False


# 全局单例实例
_semantic_highlight_service = None
_service_lock = threading.Lock()


def get_semantic_highlight_service(
    model_path: Optional[str] = None,
    enabled: bool = True,
    threshold: float = 0.5
) -> SemanticHighlightService:
    """
    获取语义高亮服务单例
    
    Args:
        model_path: 模型路径（可选，默认使用标准路径）
        enabled: 是否启用（可选）
        threshold: 阈值（可选）
    
    Returns:
        SemanticHighlightService 实例
    """
    global _semantic_highlight_service
    
    with _service_lock:
        if _semantic_highlight_service is None:
            _semantic_highlight_service = SemanticHighlightService(
                model_path=model_path or "/home/songbinbin/Proj/hf_models/semantic-highlight-bilingual-v1",
                enabled=enabled,
                threshold=threshold
            )
        return _semantic_highlight_service
