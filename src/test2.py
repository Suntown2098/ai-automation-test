import os
import json
import re
from typing import List, Dict, Any, Optional, Tuple
import tiktoken
from pathlib import Path
import numpy as np
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import FAISS
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.schema.document import Document
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate

# Configuration
INSTRUCTION_DIR = "instructions"  # Directory containing instruction markdown files
UI_SCHEMA_DIR = "ui_schemas"       # Directory containing UI schema JSON files
VECTOR_DB_PATH = "vector_db"       # Path to save vector databases
OVERLAP_TOKENS = 25                # Token overlap between chunks
TARGET_CHUNK_TOKENS = 120          # Target number of tokens per chunk
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")  # Get API key from environment

# Initialize tokenizer for chunk size estimation
tokenizer = tiktoken.get_encoding("cl100k_base")  # Compatible with OpenAI embeddings

class WMSTestAutomationAgent:
    def __init__(self):
        self.instruction_vectorstore = None
        self.ui_schema_vectorstore = None
        self.llm = ChatOpenAI(
            model="gpt-4o",  # You can replace with Claude model when using their API
            temperature=0.2,
        )
        self.embeddings = OpenAIEmbeddings()
    
    def initialize(self) -> None:
        """Initialize the agent by loading or creating vector stores"""
        # Check if vector stores exist, if not create them
        instruction_db_path = os.path.join(VECTOR_DB_PATH, "instructions")
        ui_schema_db_path = os.path.join(VECTOR_DB_PATH, "ui_schemas")
        
        if os.path.exists(instruction_db_path) and os.path.exists(ui_schema_db_path):
            print("Loading existing vector stores...")
            self.instruction_vectorstore = FAISS.load_local(instruction_db_path, self.embeddings)
            self.ui_schema_vectorstore = FAISS.load_local(ui_schema_db_path, self.embeddings)
        else:
            print("Creating new vector stores...")
            os.makedirs(VECTOR_DB_PATH, exist_ok=True)
            self._create_vector_stores()
    
    def _create_vector_stores(self) -> None:
        """Create vector stores for instructions and UI schemas"""
        # Process instruction files
        instruction_docs = self._process_instruction_files()
        instruction_chunks = self._chunk_instructions(instruction_docs)
        self.instruction_vectorstore = FAISS.from_documents(instruction_chunks, self.embeddings)
        self.instruction_vectorstore.save_local(os.path.join(VECTOR_DB_PATH, "instructions"))
        
        # Process UI schema files
        ui_schema_docs = self._process_ui_schema_files()
        self.ui_schema_vectorstore = FAISS.from_documents(ui_schema_docs, self.embeddings)
        self.ui_schema_vectorstore.save_local(os.path.join(VECTOR_DB_PATH, "ui_schemas"))
    
    def _process_instruction_files(self) -> List[Document]:
        """Process markdown instruction files and convert to documents"""
        docs = []
        instruction_dir = Path(INSTRUCTION_DIR)
        
        for file_path in instruction_dir.glob("*.md"):
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
                metadata = {
                    "source": file_path.name,
                    "type": "instruction",
                    "title": self._extract_title(content) or file_path.stem
                }
                docs.append(Document(page_content=content, metadata=metadata))
        
        return docs
    
    def _extract_title(self, content: str) -> Optional[str]:
        """Extract title from markdown content if available"""
        # Try to find an h1 header or the first line
        match = re.search(r"^# (.+)$", content, re.MULTILINE)
        if match:
            return match.group(1).strip()
        
        # If no h1 header, use first non-empty line
        lines = content.split("\n")
        for line in lines:
            if line.strip():
                return line.strip()
        return None
    
    def _chunk_instructions(self, docs: List[Document]) -> List[Document]:
        """Chunk instruction documents into smaller pieces preserving task boundaries"""
        chunked_docs = []
        
        for doc in docs:
            content = doc.page_content
            metadata = doc.metadata.copy()
            
            # Split by task boundaries (headers, bullet points, numbered lists)
            task_sections = self._split_by_task_boundaries(content)
            
            # Further chunk large sections
            for i, section in enumerate(task_sections):
                # Skip empty sections
                if not section.strip():
                    continue
                
                # Estimate token count
                tokens = len(tokenizer.encode(section))
                
                if tokens <= TARGET_CHUNK_TOKENS * 1.5:
                    # Keep section as is if it's reasonably sized
                    section_metadata = metadata.copy()
                    section_metadata["chunk_index"] = i
                    chunked_docs.append(Document(page_content=section, metadata=section_metadata))
                else:
                    # Further chunk large sections
                    text_splitter = RecursiveCharacterTextSplitter(
                        chunk_size=TARGET_CHUNK_TOKENS,
                        chunk_overlap=OVERLAP_TOKENS,
                        length_function=lambda x: len(tokenizer.encode(x)),
                    )
                    sub_chunks = text_splitter.create_documents([section], [metadata])[0]
                    
                    # Update metadata for sub-chunks
                    for j, chunk in enumerate(sub_chunks):
                        chunk.metadata["chunk_index"] = f"{i}.{j}"
                    
                    chunked_docs.extend(sub_chunks)
        
        return chunked_docs
    
    def _split_by_task_boundaries(self, content: str) -> List[str]:
        """Split content by natural task boundaries"""
        # Look for headers, bullet points, and numbered steps
        # This regex pattern matches markdown headers, bullet points, and numbered items 
        pattern = r"(^#{1,6}\s.+$)|(^\s*[-*]\s.+$)|(^\s*\d+\.\s.+$)"
        
        # Find all matches
        matches = list(re.finditer(pattern, content, re.MULTILINE))
        
        if not matches:
            # If no structure found, return the whole content
            return [content]
        
        sections = []
        for i in range(len(matches)):
            start_pos = matches[i].start()
            # End position is either the start of the next section or the end of the content
            end_pos = matches[i+1].start() if i < len(matches) - 1 else len(content)
            sections.append(content[start_pos:end_pos])
        
        return sections
    
    def _process_ui_schema_files(self) -> List[Document]:
        """Process UI schema JSON files and convert to documents"""
        docs = []
        ui_schema_dir = Path(UI_SCHEMA_DIR)
        
        for file_path in ui_schema_dir.glob("*.json"):
            with open(file_path, "r", encoding="utf-8") as f:
                try:
                    schema = json.load(f)
                    
                    # Extract component name and description for metadata
                    component_name = schema.get("component", "") or schema.get("name", file_path.stem)
                    description = schema.get("description", "")
                    
                    # Create a document for the overall schema
                    metadata = {
                        "source": file_path.name,
                        "type": "ui_schema",
                        "component": component_name,
                        "description": description
                    }
                    
                    # Keep the original JSON as the content
                    docs.append(Document(page_content=json.dumps(schema), metadata=metadata))
                    
                    # Create separate documents for each section if sections exist
                    if "sections" in schema:
                        for section in schema["sections"]:
                            section_name = section.get("name", "")
                            section_desc = section.get("description", "")
                            
                            section_metadata = metadata.copy()
                            section_metadata.update({
                                "section_name": section_name,
                                "section_description": section_desc
                            })
                            
                            docs.append(Document(
                                page_content=json.dumps(section),
                                metadata=section_metadata
                            ))
                except json.JSONDecodeError:
                    print(f"Error parsing JSON file: {file_path}")
        
        return docs
    
    def run_test(self, test_command: str) -> Dict[str, Any]:
        """Process a test command and generate test steps"""
        # 1. Parse test command
        test_type = self._parse_test_command(test_command)
        
        # 2. Retrieve relevant instruction document
        instruction_docs = self._retrieve_instructions(test_type)
        
        if not instruction_docs:
            return {"error": f"No instructions found for: {test_type}"}
        
        # 3. Break down instruction into steps
        steps = self._break_down_instructions(instruction_docs[0])
        
        # 4. Generate test steps for each instruction step
        test_steps = []
        for step in steps:
            # Retrieve UI schema for this step
            ui_schema = self._retrieve_ui_schema(step)
            
            # Generate test action for this step using the UI schema
            test_action = self._generate_test_action(step, ui_schema)
            test_steps.append(test_action)
        
        return {"test_steps": test_steps}
    
    def _parse_test_command(self, command: str) -> str:
        """Parse the test command to extract test type"""
        # Simple parsing - extract keywords after "test"
        match = re.search(r"test\s+(.+)$", command, re.IGNORECASE)
        if match:
            return match.group(1).strip()
        return command
    
    def _retrieve_instructions(self, test_type: str) -> List[Document]:
        """Retrieve instruction documents from vector store"""
        results = self.instruction_vectorstore.similarity_search(
            f"Instructions for {test_type}", k=1
        )
        return results
    
    def _break_down_instructions(self, instruction_doc: Document) -> List[str]:
        """Break down instruction document into individual steps"""
        # Create a prompt for the LLM to break down the instructions
        prompt = ChatPromptTemplate.from_messages([
            ("system", """
            You are an expert in breaking down software test instructions into individual steps. 
            Given a set of instructions for testing a warehouse management system (WMS) web application, 
            break them down into clear, atomic steps that can be automated.
            
            Each step should be a single action that can be performed by a test automation tool.
            """),
            ("user", """
            Please break down the following WMS test instructions into individual steps.
            Each step should be atomic and should correspond to a single UI interaction.
            
            INSTRUCTIONS:
            {instructions}
            """)
        ])
        
        # Get response from LLM
        response = self.llm.invoke(prompt.format(instructions=instruction_doc.page_content))
        
        # Extract steps from response
        steps = []
        for line in response.content.split("\n"):
            if line.strip() and not line.startswith("#"):
                steps.append(line.strip())
        
        return steps
    
    def _retrieve_ui_schema(self, step: str) -> Optional[Dict[str, Any]]:
        """Retrieve relevant UI schema for a given step"""
        results = self.ui_schema_vectorstore.similarity_search(
            f"UI schema for step: {step}", k=2
        )
        
        if not results:
            return None
        
        # Try to parse the schema from the documents
        schemas = []
        for doc in results:
            try:
                schema = json.loads(doc.page_content)
                schemas.append(schema)
            except json.JSONDecodeError:
                pass
        
        # For simplicity, return the first valid schema
        return schemas[0] if schemas else None
    
    def _generate_test_action(self, step: str, ui_schema: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Generate test action for a given step using UI schema"""
        prompt = ChatPromptTemplate.from_messages([
            ("system", """
            You are an expert in generating Selenium-based test actions from instructions and UI schemas.
            Given a test step instruction and a UI schema, generate a structured test action in the format:
            
            {
                "step": {
                    "action": "[action type: click, text-enter, select]",
                    "element_id": "[element ID from UI schema]",
                    "text": "[text to enter if applicable, otherwise empty string]",
                    "component_name": "[component name from UI schema]",
                    "description": "[human-readable description of the step]"
                }
            }
            
            Valid action types are:
            - click: For buttons, checkboxes, tabs
            - text-enter: For text inputs, date pickers
            - select: For dropdowns, select fields
            """),
            ("user", """
            Generate a test action for the following step:
            
            STEP: {step}
            
            Available UI Schema:
            {ui_schema}
            
            Return only a valid JSON object with the test action.
            """)
        ])
        
        ui_schema_str = json.dumps(ui_schema) if ui_schema else "No UI schema available"
        
        # Get response from LLM
        response = self.llm.invoke(prompt.format(step=step, ui_schema=ui_schema_str))
        
        # Parse the JSON response
        try:
            # Extract JSON from response (it might contain markdown code blocks)
            json_match = re.search(r"```json\s*(.+?)\s*```", response.content, re.DOTALL)
            json_str = json_match.group(1) if json_match else response.content
            
            # Remove any non-JSON text
            json_str = re.sub(r"[^{]*([\s\S]*?})[^}]*", r"\1", json_str)
            
            return json.loads(json_str)
        except (json.JSONDecodeError, AttributeError) as e:
            # Fallback for when JSON parsing fails
            return {
                "step": {
                    "action": "unknown",
                    "element_id": "unknown",
                    "text": "",
                    "component_name": "unknown",
                    "description": f"Could not generate action for: {step}. Error: {str(e)}"
                }
            }

# Command-line interface
def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="WMS Test Automation Agent")
    parser.add_argument("--init", action="store_true", help="Initialize or update vector database")
    parser.add_argument("--test", type=str, help="Test command to execute", default=None)
    
    args = parser.parse_args()
    
    agent = WMSTestAutomationAgent()
    
    if args.init:
        # Force recreation of vector stores
        if os.path.exists(VECTOR_DB_PATH):
            import shutil
            shutil.rmtree(VECTOR_DB_PATH)
        agent._create_vector_stores()
        print("Vector stores created successfully.")
    else:
        # Normal initialization
        agent.initialize()
    
    if args.test:
        # Run test command
        result = agent.run_test(args.test)
        print(json.dumps(result, indent=2))

if __name__ == "__main__":
    main()