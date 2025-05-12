import os
import json
import numpy as np
from typing import List, Dict, Any, Optional, Tuple, Literal
from pathlib import Path
import logging
from pydantic import BaseModel, Field
from openai import OpenAI

import faiss
from langchain_openai import OpenAIEmbeddings
from langchain_core.documents import Document
from langchain_community.docstore.in_memory import InMemoryDocstore
from langchain_community.vectorstores import FAISS
from uuid import uuid4
from dotenv import load_dotenv


class Element:
    label: str
    id: str
    description: str
    element_type: Literal["input-text", "input-password", "input-date", "button", "dropdown", "dropdown-item", "checkbox", "tab"]
    children: Optional[List["Element"]] = None # for dropdown and grid 

class Section:
    name: str
    description: str
    elements: List[Element]


class Schema:
    name: str
    description: str
    sections: List[Section]

# Configuration
VECTOR_DB_PATH = "vector_db"  

class BaseRAGManager:
    """
    Base class for managing RAG components.
    """
    def __init__(self, dimension: int = 1536):
        """
        Initialize the Base RAG manager.

        Args:
            folder: Path to files to be indexed
        """
        self.folder = None
        self.client = None
        self.embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
        # self.index = faiss.IndexFlatL2(dimension)  # L2 distance for similarity
        self.index = faiss.IndexFlatL2(dimension)
        self.vector_store = None

    # def _load_data(self) -> List[Document]:
    #     pass
    
    # def _create_vector_store(self, documents: List[Document]) -> None:
    #     db_path = f'{VECTOR_DB_PATH}_{self.folder}'
    #     """Create vector stores for instructions and UI schemas"""
    #     uuids = [str(uuid4()) for _ in range(len(documents))]

    #     # Add docs to vector store instruction files
    #     try :
    #         self.vector_store.add_documents(documents=documents, ids=uuids)
    #         self.vector_store.save_local(db_path)
    #         print(f"Vector store created and saved at {db_path}")
    #     except Exception as e:
    #         print(f"Error creating vector store: {e}")
    #         raise e

    # def _initialize_vector_store(self) -> None:
    #     """Initialize the agent by loading or creating vector stores"""
    #     # Check if vector stores exist, if not create them
    #     db_path = f'{VECTOR_DB_PATH}_{self.folder}'
        
    #     if os.path.exists(db_path) and os.listdir(db_path):
    #         print("Loading existing vector stores...")
    #         self.vector_store = FAISS.load_local(db_path, self.embeddings, allow_dangerous_deserialization=True)
    #     else:
    #         print("Creating new vector stores...")
    #         os.makedirs(db_path, exist_ok=True)
    #         self.vector_store = FAISS(
    #                             embedding_function=self.embeddings,
    #                             index=self.index,
    #                             docstore=InMemoryDocstore(),
    #                             index_to_docstore_id={},
    #                         )
            
    #         docs = self._load_data()
    #         self._create_vector_store(docs)

    def search(self, query: str, k: int = 1) -> Optional[Dict[str, Any]]:
        """
        Search for relevant documents in the vector store.
        Returns the file content.
        """
        results = self.vector_store.similarity_search(
            query,
            k=k,
        )

        # Check if results are empty
        if not len(results):
            print(f"No results found for query: {query}")
            return None
        
        for res in results:
            print(f"* {res.page_content} [{res.metadata}]")
        
        contents = []
        # Extract the content of file from metadata
        for result in results:
            file_path = result.metadata.get("source")
            # Join the folder path with the file name
            root_dir = Path(self.folder).resolve()

            # Check if the folder exists
            if not root_dir.exists():
                raise FileNotFoundError(f"The folder {root_dir} does not exist.")
            
            full_path = os.path.join(root_dir, file_path)
            # Check if the file exists
            with open(full_path, "r", encoding="utf-8") as f:
            # with open(full_path, "r") as f:
                content = f.read()
                contents.append(content)

        return contents
    

class InstructionRAGManager(BaseRAGManager):
    """
    Manages the RAG components for instruction files.
    """
    def __init__(self):
        """
        Initialize the Instruction RAG manager.

        Args:
            client: OpenAI client
            folder: Path to instruction files to be indexed
        """
        super().__init__()
        self.folder = "instructions_vn"

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not found in .env file")

        self.client = OpenAI(api_key=api_key)
        self._initialize_vector_store()
    
    def _summarize_content(self, content: str) -> str:
        """
        Summarize the content of a given instruction.
        """
        prompt = (
            "You are given a set of instructions for testing a warehouse management system (WMS) web application."
            "Your task is to give brief description of what is this instruction about.\n\n"
            f"INSTRUCTIONS:\n{content}\n\n"
            "SUMMARY:"

            "Rules:\n"
            "1. Only summarize the content by numbered list, do not add any additional information.\n"
            "2. Do not include any examples \"Hướng dẫn các bước tạo mới một đơn hàng nhập (Receipt) trên hệ thống WMS. Cụ thể:\"\n"
        )
        try:
            # Get response from the OpenAI client
            response = self.client.completions.create(
                model="o4-mini",
                prompt=prompt,
                max_tokens=500
                # temperature=0
            )
            return response.choices[0].text.strip()
        except Exception as e:
            print(f"Error breaking down instruction: {e}")
            return ''
        
    def _load_data(self) -> List[Document]:
        """
        Load the title of instruction files only, not the whole content.
        """
        docs = []

        # Ensure the folder path is resolved correctly
        instruction_dir = Path(self.folder).resolve()

        # Check if the folder exists
        if not instruction_dir.exists():
            raise FileNotFoundError(f"The folder {instruction_dir} does not exist.")

        for file_path in instruction_dir.glob("*.txt"):
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
                summary_content = self._summarize_content(content)
                metadata = {
                    "source": file_path.name
                }
                print(f"File: {file_path.name}")
                docs.append(Document(page_content=summary_content, metadata=metadata))
        
        return docs
    
    def _create_vector_store(self, documents: List[Document]) -> None:
        db_path = f'{VECTOR_DB_PATH}_{self.folder}'
        """Create vector stores for instructions and UI schemas"""
        uuids = [str(uuid4()) for _ in range(len(documents))]

        # Add docs to vector store instruction files
        try :
            self.vector_store.add_documents(documents=documents, ids=uuids)
            self.vector_store.save_local(db_path)
            print(f"Vector store created and saved at {db_path}")
        except Exception as e:
            print(f"Error creating vector store: {e}")
            raise e

    def _initialize_vector_store(self) -> None:
        """Initialize the agent by loading or creating vector stores"""
        # Check if vector stores exist, if not create them
        db_path = f'{VECTOR_DB_PATH}_{self.folder}'
        
        if os.path.exists(db_path) and os.listdir(db_path):
            print("Loading existing vector stores...")
            self.vector_store = FAISS.load_local(db_path, self.embeddings, allow_dangerous_deserialization=True)
        else:
            print("Creating new vector stores...")
            os.makedirs(db_path, exist_ok=True)
            self.vector_store = FAISS(
                                embedding_function=self.embeddings,
                                index=self.index,
                                docstore=InMemoryDocstore(),
                                index_to_docstore_id={},
                            )
            
            docs = self._load_data()
            self._create_vector_store(docs)
    
    def break_down_instruction(self, instruction: str) -> List[str]:
        """
        Break down the instruction into steps.

        Args:
            instruction: The instruction text provided by the user.

        Returns:
            A list of steps extracted from the instruction.
        """
        # Load the system prompt from step_breakdown_prompt.txt
        prompt_file_path = Path(__file__).parent / 'prompt' / 'step_breakdown_prompt.txt'
        try:
            with open(prompt_file_path, 'r', encoding='utf-8') as file:
                system_prompt = file.read()
        except FileNotFoundError:
            print(f"System prompt file not found at {prompt_file_path}")
            return []
        except Exception as e:
            print(f"Error reading system prompt file: {e}")
            return []

        # Format the prompt with the user-provided instruction
        formatted_prompt = system_prompt.replace("{instruction}", instruction)

        try:
            # Get response from the OpenAI client
            response = self.client.completions.create(
                model="o4-mini",
                prompt=formatted_prompt,
                max_tokens=500,
                temperature=0.7
            )
            # Extract steps from the response
            return response.choices[0].text.strip().split("\n")
        except Exception as e:
            print(f"Error breaking down instruction: {e}")
            return []


class UIComponentRAGManager(BaseRAGManager):
    """
    Manages the RAG components for UI component markdown files.
    """
    UI_COMPONENT_DIR = "markdown"

    def __init__(self):
        super().__init__()
        self.folder = "markdown"
        self._initialize_vector_store()

    def _load_data(self) -> List[Document]:
        """
        Load the name and description of UI schema only, not the whole content.
        """
        docs = []
        ui_schema_dir = Path(self.folder)

        for file_path in ui_schema_dir.glob("*.json"):
            with open(file_path, 'r') as f:
                data = json.load(f)
                text_to_embed = f"{data.get('name', '')} - {data.get('description', '')}"
                metadata = {
                    "source": file_path.name
                }
                print(f"File: {file_path.name}")
                docs.append(Document(page_content=text_to_embed, metadata=metadata))
        
        return docs
    
    def _create_vector_store(self, documents: List[Document]) -> None:
        db_path = f'{VECTOR_DB_PATH}_{self.folder}'
        """Create vector stores for instructions and UI schemas"""
        uuids = [str(uuid4()) for _ in range(len(documents))]

        # Add docs to vector store instruction files
        try :
            self.vector_store.add_documents(documents=documents, ids=uuids)
            self.vector_store.save_local(db_path)
            print(f"Vector store created and saved at {db_path}")
        except Exception as e:
            print(f"Error creating vector store: {e}")
            raise e

    def _initialize_vector_store(self) -> None:
        """Initialize the agent by loading or creating vector stores"""
        # Check if vector stores exist, if not create them
        db_path = f'{VECTOR_DB_PATH}_{self.folder}'
        
        if os.path.exists(db_path) and os.listdir(db_path):
            print("Loading existing vector stores...")
            self.vector_store = FAISS.load_local(db_path, self.embeddings, allow_dangerous_deserialization=True)
        else:
            print("Creating new vector stores...")
            os.makedirs(db_path, exist_ok=True)
            self.vector_store = FAISS(
                                embedding_function=self.embeddings,
                                index=self.index,
                                docstore=InMemoryDocstore(),
                                index_to_docstore_id={},
                            )
            
            docs = self._load_data()
            self._create_vector_store(docs)