import os
import json
import numpy as np
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
import logging
import faiss
from openai import OpenAI


class VectorStore:
    """
    Vector store for storing and retrieving embeddings for RAG.
    """
    def __init__(self, dimension: int = 1536):
        """
        Initialize the vector store.
        
        Args:
            dimension: Dimension of the embeddings
        """
        self.dimension = dimension
        # self.index = faiss.IndexFlatL2(dimension)  # L2 distance for similarity
        self.index = faiss.IndexFlatIP(dimension)
        self.metadata = []

    def normalize_vectors(self, vectors):
        faiss.normalize_L2(vectors)
        return vectors

    def add_vectors(self, vectors: List[np.ndarray], metadata_list: List[Dict[str, Any]]):
        """
        Add vectors to the index.
        
        Args:
            vectors: List of embeddings
            metadata_list: List of metadata dictionaries corresponding to the vectors
        """
        if len(vectors) == 0:
            return
            
        # Convert to numpy array if not already
        embeddings_np = np.array(vectors).astype('float32')
        
        # Add to index
        embeddings_np = self.normalize_vectors(embeddings_np)
        self.index.add(embeddings_np)
        
        # Store metadata
        self.metadata.extend(metadata_list)
        
    def search(self, query_vector: np.ndarray, k: int = 5) -> List[Dict[str, Any]]:
        """
        Search for similar vectors.
        
        Args:
            query_vector: Query embedding
            k: Number of results to return
            
        Returns:
            List of metadata for similar vectors
        """
        # Ensure we don't request more results than we have
        k = min(k, len(self.metadata))
        if k == 0 or self.index.ntotal == 0:
            return []
            
        # Convert to numpy array if not already
        query_np = np.array([query_vector]).astype('float32')
        
        # Search
        distances, indices = self.index.search(query_np, k)
        
        # Get metadata for results
        results = []
        for i, idx in enumerate(indices[0]):
            if idx < len(self.metadata):  # Ensure index is valid
                result = self.metadata[idx].copy()
                result['distance'] = float(distances[0][i])
                results.append(result)
                
        return results


class RAGManager:
    """
    Manages the RAG components for the test agent.
    """
    def __init__(self, client: OpenAI, instruction_folder: Path, markdown_folder: Path):
        """
        Initialize the RAG manager.
        
        Args:
            client: OpenAI client
            instruction_folder: Path to instruction files
            markdown_folder: Path to markdown files
        """
        self.client = client
        self.instruction_folder = instruction_folder
        self.markdown_folder = markdown_folder
        
        # Vector stores
        self.instruction_store = VectorStore()
        self.markdown_store = VectorStore()
        
        # Cache
        self.embedding_cache = {}
        
    def get_embedding(self, text: str) -> np.ndarray:
        """
        Get embedding for a text.
        
        Args:
            text: Text to embed
            
        Returns:
            Embedding vector
        """
        # Use cache if available
        if text in self.embedding_cache:
            return self.embedding_cache[text]
            
        try:
            # Get embedding from API
            response = self.client.embeddings.create(
                model="text-embedding-3-small",
                input=text
            )
            embedding = response.data[0].embedding
            
            # Cache embedding
            self.embedding_cache[text] = embedding
            
            return embedding
        except Exception as e:
            #logger.error(f"Error getting embedding: {e}")
            # Return zero vector as fallback
            return np.zeros(1536)
            
    def index_instructions(self):
        """Index all instruction files."""
        #logger.info("Indexing instruction files...")
        
        instruction_files = list(self.instruction_folder.glob("*.md"))
        vectors = []
        metadata_list = []
        
        for file_path in instruction_files:
            try:
                # Read file
                with open(file_path, 'r') as f:
                    content = f.read()
                    
                # Clean content (remove # symbols and extra whitespace)
                cleaned_content = content.replace('#', ' ').strip()
                
                # Get embedding
                embedding = self.get_embedding(cleaned_content)
                
                # Create metadata
                metadata = {
                    'file_path': str(file_path),
                    'file_name': file_path.stem,
                    'content': content
                }
                
                vectors.append(embedding)
                metadata_list.append(metadata)
                
            except Exception as e:
                print(f"Error indexing instruction file {file_path}: {e}")
                #logger.error(f"Error indexing instruction file {file_path}: {e}")
                
        # Add to vector store
        self.instruction_store.add_vectors(vectors, metadata_list)
        #logger.info(f"Indexed {len(vectors)} instruction files")
        
    def index_markdown_files(self):
        """Index all markdown representation files."""
        #logger.info("Indexing markdown representation files...")
        
        markdown_files = list(self.markdown_folder.glob("*.json"))
        vectors = []
        metadata_list = []
        
        for file_path in markdown_files:
            try:
                # Read file
                with open(file_path, 'r') as f:
                    data = json.load(f)
                    
                # Combine content fields for embedding
                text_to_embed = f"{data.get('markdown_description', '')} {data.get('explanation', '')}"
                
                # Get embedding
                embedding = self.get_embedding(text_to_embed)
                
                # Create metadata
                metadata = {
                    'file_path': str(file_path),
                    'file_name': file_path.stem,
                    'description': data.get('markdown_description', ''),
                    'explanation': data.get('explanation', ''),
                    'content': data.get('content', '')
                }
                
                vectors.append(embedding)
                metadata_list.append(metadata)
                
            except Exception as e:
                print(f"Error indexing markdown file {file_path}: {e}")
                #logger.error(f"Error indexing markdown file {file_path}: {e}")
                
        # Add to vector store
        self.markdown_store.add_vectors(vectors, metadata_list)
        #logger.info(f"Indexed {len(vectors)} markdown files")
        
    def find_instruction_file(self, task_description: str) -> Optional[Dict[str, Any]]:
        """
        Find the most relevant instruction file based on semantic similarity.
        
        Args:
            task_description: Natural language description of the task
            
        Returns:
            Metadata of the most relevant instruction file or None if not found
        """
        # Get embedding for query
        query_embedding = self.get_embedding(task_description)
        
        # Search for similar instruction files
        results = self.instruction_store.search(query_embedding, k=1)
        
        if results:
            #logger.info(f"Found relevant instruction file: {results[0]['file_name']} (distance: {results[0]['distance']:.4f})")
            return results[0]
        else:
            #logger.warning("No relevant instruction file found")
            return None
            
    def find_relevant_components(self, instruction: str, top_k: int = 3, threshold: float = 1.5) -> List[Dict[str, Any]]:
        """
        Find the most relevant component markdown files for an instruction step.
        
        Args:
            instruction: Instruction step text
            top_k: Maximum number of components to return
            threshold: Maximum distance threshold for inclusion
            
        Returns:
            List of relevant component metadata
        """
        # Get embedding for query
        query_embedding = self.get_embedding(instruction)
        
        # Search for similar markdown files
        results = self.markdown_store.search(query_embedding, k=top_k)
        
        # Filter by distance threshold
        filtered_results = [r for r in results if r['distance'] < threshold]
        
        if filtered_results:
            component_names = [r['file_name'] for r in filtered_results]
            #logger.info(f"Found relevant components for '{instruction}': {component_names}")
            return filtered_results
        else:
            #logger.warning(f"No relevant components found for '{instruction}', using fallbacks")
            # Return default components as fallback
            return [r for r in results[:2]]  # Return top 2 as fallback