# isolated module for sentiment analysis
# ML logic separated from de db query logic

import logging
import torch
from transformers import pipeline

# STRICT CPU LIMIT: Leave 1 vCPU free for OS, Postgres, and Qdrant
torch.set_num_threads(2)

logger = logging.getLogger(__name__)

class FinancialSentimentAnalyzer:
    def __init__(self):
        self.model_name = "ProsusAI/finbert"

        # Dynamic Device Selection: GPU for local development, CPU fallback for VPS compatibility
        # 0 = GPU, -1 = CPU
        # torch.cuda.is_available() checks if a GPU is available (Pytorch detects if CUDA is installed)
        if torch.cuda.is_available():
            self.device = 0
            device_name = f"CUDA ({torch.cuda.get_device_name(0)})"
        elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            self.device = "mps"
            device_name = "MPS (Apple Silicon)"
        else:
            self.device = -1
            device_name = "CPU"

        logger.info(f"Loading ML model: {self.model_name} on {device_name}...")

        self.classifier = pipeline(
            "sentiment-analysis",
            model=self.model_name,
            tokenizer=self.model_name,
            device=self.device,
            truncation=True,

            # max_length is the maximum number of tokens the model can process
            max_length=512,

            # top_k=None tells the model to return all possible outputs (positive, negative, neutral), not just the winner one
            top_k=None
        )

        logger.info("ML model loaded successfully")

    def analyze(self, text: str) -> dict:
        try:
            if not text:
                return {
                    "sentiment_label": "neutral", 
                    "sentiment_score": 0.0
                }

            # Example output: [{'label': 'positive', 'score': 0.98}, {'label': 'neutral', 'score': 0.01}, {'label': 'negative', 'score': 0.01}]
            result = self.classifier(text)[0]

            scores = {item['label']: item['score'] for item in result}

            # Quant Formula: (Positive - Negative) * (1 - Neutral)
            impact_score = round((scores['positive'] - scores['negative']) * (1 - scores['neutral']), 4)

            # label is either 'positive', 'negative', 'neutral'
            dominant_label = max(scores, key=scores.get)

            return {
                "sentiment_label": dominant_label,
                "sentiment_score": impact_score
            }
        except Exception as e:
            logger.error(f"Inference failed: {e}", exc_info=True) # exc_info=True logs the full stack trace
            return {"sentiment_label": None, "sentiment_score": None}

