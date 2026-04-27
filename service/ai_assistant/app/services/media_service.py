"""
媒体处理服务模块

功能介绍：
-----------
本模块负责将多模态输入（图像、音频）转换为文本，供后续查询处理使用。

功能列表：
- image_to_text(): 图像内容理解与 OCR（使用 DashScope 多模态对话 API）
- audio_to_text(): 语音转文字（使用 DashScope ASR API）

图像处理：
- 自动调整过大图像尺寸（最长边 1024px）
- 超大文件自动压缩为 JPEG 格式
- 统一以 data URL 形式提交给多模态模型

音频处理：
- 使用 ffmpeg 将任意格式音频转换为 16kHz 单声道 WAV
- 写入临时文件后调用 ASR 接口
- 自动清理临时文件
"""
from __future__ import annotations

import base64
import io
import subprocess
from PIL import Image

import dashscope
from dashscope import MultiModalConversation
from dashscope.audio.asr import Recognition

from app.config import settings
from app.utils.logger import logger

dashscope.api_key = settings.ALI_API_KEY


def _resize_image_if_needed(image_base64: str, max_size: int = 1024) -> str:
    """
    检查并调整图像大小，避免 DashScope API 有效载荷过大。
    
    处理逻辑：
        - 最长边超过 max_size 时等比例缩放
        - Base64 超过 1MB 时重新压缩为 JPEG
        - 处理失败时返回原始内容
    
    参数:
        image_base64: Base64 编码的图像。
        max_size: 最长边允许的最大像素值。
    
    返回:
        优化后的 Base64 编码图像。
    """
    try:
        image_data = base64.b64decode(image_base64)
        image = Image.open(io.BytesIO(image_data))
        
        width, height = image.size
        
        # 检查是否需要调整大小
        if max(width, height) > max_size:
            logger.info("Image resize triggered: original={}x{}", width, height)
            ratio = max_size / max(width, height)
            new_size = (int(width * ratio), int(height * ratio))
            image = image.resize(new_size, Image.Resampling.LANCZOS)
            
            buffer = io.BytesIO()
            if image.mode in ('RGBA', 'P'):
                image = image.convert('RGB')
            image.save(buffer, format="JPEG", quality=85)
            logger.info("Image resized: new={}x{}", new_size[0], new_size[1])
            return base64.b64encode(buffer.getvalue()).decode('utf-8')
        
        # 即使尺寸较小，如果文件体积巨大（例如未压缩的 PNG），也转换为 JPEG
        if len(image_base64) > 1 * 1024 * 1024:  # > 1MB
            logger.info("Image recompress triggered by size: base64_len={}", len(image_base64))
            buffer = io.BytesIO()
            if image.mode in ('RGBA', 'P'):
                image = image.convert('RGB')
            # 如果已经是 JPEG，可能只是重新保存，但确保压缩
            image.save(buffer, format="JPEG", quality=85)
            return base64.b64encode(buffer.getvalue()).decode('utf-8')
            
        return image_base64
    except Exception as e:
        # 如果图像处理失败，返回原始内容并由 API 处理（或在 API 端失败）
        logger.exception("Image resize failed")
        return image_base64


def _convert_audio_to_wav(audio_base64: str) -> bytes:
    """
    使用 ffmpeg 将任意格式音频转换为标准 WAV 格式。
    
    输出规格：WAV 格式、单声道、16000Hz 采样率。
    通过 subprocess 直接调用 ffmpeg，避免 pydub 等 Python 依赖问题。
    
    参数:
        audio_base64: Base64 编码的音频数据。
    
    返回:
        WAV 格式的音频字节数据。
    
    异常:
        RuntimeError: ffmpeg 转换失败。
    """
    try:
        audio_data = base64.b64decode(audio_base64)
        logger.info("Audio decode success: raw_bytes={}", len(audio_data))
        
        # 直接通过 subprocess 使用 ffmpeg，以避免 Python 依赖问题 (pydub/audioop)
        # 转换为 WAV，单声道，16kHz 采样率
        command = [
            "ffmpeg",
            "-y",            # 无需确认直接覆盖输出文件
            "-i", "pipe:0",  # 从标准输入读取
            "-f", "wav",     # 输出格式为 wav
            "-ac", "1",      # 音频通道: 1 (单声道)
            "-ar", "16000",  # 音频采样率: 16000Hz
            "pipe:1"         # 输出到标准输出
        ]
        
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        stdout_data, stderr_data = process.communicate(input=audio_data)
        
        if process.returncode != 0:
            error_msg = stderr_data.decode("utf-8", errors="ignore")
            # 记录错误但抛出简洁的异常
            logger.error("FFmpeg convert failed: code={}, err={}", process.returncode, error_msg[:300])
            raise RuntimeError(f"FFmpeg 转换失败: {process.returncode}")
            
        logger.info("Audio converted to wav: wav_bytes={}", len(stdout_data))
        return stdout_data
        
    except Exception as e:
        logger.exception("Audio conversion failed")
        # 为了调试提供更好的错误消息
        raise RuntimeError(f"处理音频文件失败: {e}")


async def image_to_text(image_base64: str) -> str:
    """
    使用多模态模型理解图像内容并提取文字。
    
    参数:
        image_base64: Base64 编码的图像（JPEG/PNG）。
    
    返回:
        图像内容的自然语言描述文本。
    
    异常:
        RuntimeError: DashScope API 调用失败。
    """
    # 发送前优化图像大小
    logger.info("Image to text start: base64_len={}", len(image_base64))
    optimized_base64 = _resize_image_if_needed(image_base64)

    # DashScope 期望图像以 data URL 形式提供
    # 由于缩放后转换为了 JPEG，强制使用 JPEG 媒体类型
    data_url = f"data:image/jpeg;base64,{optimized_base64}"
    messages = [
        {
            "role": "user",
            "content": [
                {"image": data_url},
                {"text": "请描述这张图片的内容，提取其中所有的文字和关键信息。"},
            ],
        }
    ]
    
    import asyncio
    def _call_qwen_vl():
        return MultiModalConversation.call(
            model=settings.LLM_MODEL_IMAGE_UNDERSTANDING,
            messages=messages,
        )
        
    response = await asyncio.to_thread(_call_qwen_vl)
    if response.status_code != 200:
        logger.error("Image API failed: status_code={}, message={}", response.status_code, response.message)
        raise RuntimeError(
            f"图像 API 错误: {response.status_code} – {response.message}"
        )
    text = response.output.choices[0].message.content[0].get("text", "")
    logger.info("Image to text success: text_len={}", len(text))
    return text


async def audio_to_text(audio_base64: str) -> str:
    """
    使用 DashScope ASR 将音频转录为文本。
    
    实现流程：
        1. Base64 解码并使用 ffmpeg 转换为 16kHz 单声道 WAV
        2. 写入临时文件
        3. 调用 Recognition 接口进行识别
        4. 清理临时文件
    
    参数:
        audio_base64: Base64 编码的音频（支持 WAV/MP3 等，自动转换）。
    
    返回:
        转录后的文本字符串。
    
    异常:
        RuntimeError: 音频转换失败、未检测到有效语音内容或 API 调用失败。
    """
    # 将音频转换为 WAV 格式
    logger.info("Audio to text start: base64_len={}", len(audio_base64))
    try:
        audio_wav = _convert_audio_to_wav(audio_base64)
    except RuntimeError as exc:
        logger.exception("Audio preprocessing failed")
        raise RuntimeError(f"音频处理失败: {exc}")

    import io
    # 注意: DashScope SDK 1.25.2 中 Recognition.call 是实例方法，且需要文件路径。
    
    # 1. 将音频数据写入临时文件
    import tempfile
    import os
    
    fd, tmp_file_path = tempfile.mkstemp(suffix=".wav")
    try:
        with os.fdopen(fd, 'wb') as tmp_file:
            tmp_file.write(audio_wav)
            
        # 2. 实例化 Recognition 并调用
        recognition = Recognition(
            model=settings.LLM_MODEL_SPEECH_RECOGNITION,
            format='wav',
            sample_rate=16000,
            callback=None
        )
        import asyncio
        response = await asyncio.to_thread(recognition.call, tmp_file_path)
        
    except Exception as e:
        logger.exception("ASR call failed")
        raise RuntimeError(f"DashScope ASR 错误: {e}")
    finally:
        # 3. 清理临时文件
        if os.path.exists(tmp_file_path):
            os.remove(tmp_file_path)
    
    if response.status_code != 200:
        logger.error("Audio API failed: status_code={}, message={}", response.status_code, response.message)
        raise RuntimeError(
            f"音频 API 错误: {response.status_code} – {response.message}"
        )
    
    # 检查输出中是否包含文本
    final_text = ""
    sentences = []
    
    # 尝试从不同的 DashScope SDK 格式中提取文本
    if hasattr(response, 'get_sentence') and response.get_sentence():
        sentences = response.get_sentence()
    elif hasattr(response, 'output') and response.output and 'sentence' in response.output:
        sentences = response.output['sentence']
        
    if sentences:
        text_parts = [s.get('text', '') for s in sentences if isinstance(s, dict)]
        final_text = " ".join(text_parts)
    elif hasattr(response, 'output') and response.output and hasattr(response.output, 'text'):
        final_text = str(response.output.text)
        
    final_text = final_text.strip()
    
    if not final_text:
        # 当语音全静音时，DashScope 返回 200 且 output 为 null，或者提取不到文本
        # 这会导致原代码返回 str(response) 造成大模型产生幻觉，这里主动拦截并报错
        raise RuntimeError("Task failed: 未检测到有效语音内容（可能是周围过静或说话声音太小）")

    logger.info("Audio to text success: text_len={}", len(final_text))
    return final_text
