import threading
import os
import logging
from pathlib import Path
from typing import List, Literal, Optional
import requests
import json
from pydantic import BaseModel, ValidationError, validator
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.openai import OpenAIProvider
from src.config import SYSTEM_PROMPT

from dotenv import load_dotenv

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


class GptClient:
    # Load environment variables from .env file
    path_to_env_file = Path(__file__).parent.parent / '.env'
    load_dotenv(dotenv_path=path_to_env_file, verbose = True)

    gpt_api_key = os.getenv("OPENAI_API_KEY")
    gpt_model = os.getenv("GPT_MODEL", "o4-mini")

    def __init__(self):
        logging.info("initiating GPT client model")
        logging.info(f"Using GPT model: {self.gpt_model}")
        self.system_prompt = SYSTEM_PROMPT
        # self.operation_lock = threading.Lock()

    def get_action(self, user_prompt: str):
        # Instantiate OpenAI client
        gpt_model = OpenAIModel( model_name='o4-mini', provider=OpenAIProvider(api_key=self.gpt_api_key))

        # Create a new agent
        agent = Agent(
            gpt_model,
            output_type=TestStep,
            system_prompt=self.system_prompt
        )
        result = agent.run_sync(user_prompt)
        return result


class TestStep(BaseModel):
    action: Literal["click", "enter_text", "key_enter", "scroll", "error", "finish"]
    css_selector: str
    text: str
    description: str


class Model:
    def __init__(self, gpt_api_key, system_prompt):
        self.gpt_api_key = gpt_api_key
        self.system_prompt = system_prompt

    def get_action(self, user_prompt: str) -> Optional[TestStep]:
        # Instantiate OpenAI client
        gpt_model = OpenAIModel(
            model_name='o4-mini',
            provider=OpenAIProvider(api_key=self.gpt_api_key)
        )

        # Create a new agent
        agent = Agent(
            gpt_model,
            output_type=TestStep,
            system_prompt=self.system_prompt
        )
        try:
            result = agent.run_sync(user_prompt)
            return result 
        except ValidationError as e:
            print("Model.get_action -> Validation error:", e)
            return None
        except Exception as e:
            print("Model.get_action -> An error occurred:", e)
            return e
