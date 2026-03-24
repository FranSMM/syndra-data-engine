# isolated module for sentiment analysis
# ML logic separated from de db query logic

import logging
import torch
from transformers import pipeline

logger = logging.getLogger(__name__)

class FinancialSentimentAnalyzer:
    def __init__(self):
        self.model_name = "ProsusAI/finbert"

        # 0 = GPU, -1 = CPU
        # torch.cuda.is_available() checks if a GPU is available (Pytorch detects if CUDA is installed)
        self.device = 0 if torch.cuda.is_available() else -1
        device_name = f"CUDA (GPU {torch.cuda.get_device_name(0)})" if self.device == 0 else "CPU"

        logger.info(f"Loading ML model: {self.model_name} on {device_name}...")

        self.classifier = pipeline(
            "sentiment-analysis",
            model=self.model_name,
            tokenizer=self.model_name,
            device=self.device,
            truncation=True,

            # max_length is the maximum number of tokens the model can process
            max_length=512
        )
        logger.info("ML model loaded successfully")

    def analyze(self, text: str) -> dict:
        try:
            if not text:
                return {"sentiment_label": "neutral", "sentiment_score": 0.0}

            result = self.classifier(text)[0]

            # label is either 'positive', 'negative', 'neutral'
            label = result['label'].lower()

            # convert to float between -1 and 1
            score = round(result['score'], 4)

            if label == "negative":
                score = -score
            elif label == "neutral":
                score = 0.0

            return {
                "sentiment_label": label,
                "sentiment_score": score
            }
        except Exception as e:
            logger.error(f"Inference failed: {e}", exc_info=True) # exc_info=True logs the full stack trace
            return {"sentiment_label": None, "sentiment_score": None}

