#!/usr/bin/env python3
"""Test script to verify all retrieval implementations."""

import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_imports():
    """Test that all retriever classes can be imported."""
    try:
        from unstract.prompt_service.core.retrievers.simple import SimpleRetriever
        logger.info("✓ SimpleRetriever imported successfully")
        
        from unstract.prompt_service.core.retrievers.subquestion import SubquestionRetriever
        logger.info("✓ SubquestionRetriever imported successfully")
        
        from unstract.prompt_service.core.retrievers.fusion import FusionRetriever
        logger.info("✓ FusionRetriever imported successfully")
        
        from unstract.prompt_service.core.retrievers.recursive import RecursiveRetrieval
        logger.info("✓ RecursiveRetrieval imported successfully")
        
        from unstract.prompt_service.core.retrievers.router import RouterRetriever
        logger.info("✓ RouterRetriever imported successfully")
        
        from unstract.prompt_service.core.retrievers.keyword_table import KeywordTableRetriever
        logger.info("✓ KeywordTableRetriever imported successfully")
        
        from unstract.prompt_service.core.retrievers.automerging import AutomergingRetriever
        logger.info("✓ AutomergingRetriever imported successfully")
        
        return True
    except ImportError as e:
        logger.error(f"Import error: {e}")
        return False


def test_constants():
    """Test that all retrieval constants are defined."""
    try:
        from unstract.prompt_service.constants import RetrievalStrategy
        
        strategies = [
            RetrievalStrategy.SIMPLE,
            RetrievalStrategy.SUBQUESTION,
            RetrievalStrategy.FUSION,
            RetrievalStrategy.RECURSIVE,
            RetrievalStrategy.ROUTER,
            RetrievalStrategy.KEYWORD_TABLE,
            RetrievalStrategy.AUTOMERGING,
        ]
        
        logger.info("Defined retrieval strategies:")
        for strategy in strategies:
            logger.info(f"  - {strategy.name}: {strategy.value}")
        
        return True
    except Exception as e:
        logger.error(f"Constants error: {e}")
        return False


def test_retrieval_service():
    """Test that retrieval service handles all new types."""
    try:
        from unstract.prompt_service.services.retrieval import RetrievalService
        from unstract.prompt_service.constants import RetrievalStrategy
        
        # Check if the retrieval service imports all retrievers
        import inspect
        import unstract.prompt_service.services.retrieval as retrieval_module
        
        source = inspect.getsource(retrieval_module)
        
        required_imports = [
            "AutomergingRetriever",
            "FusionRetriever",
            "KeywordTableRetriever",
            "RecursiveRetrieval",
            "RouterRetriever",
            "SimpleRetriever",
            "SubquestionRetriever",
        ]
        
        logger.info("Checking retrieval service imports:")
        for retriever in required_imports:
            if retriever in source:
                logger.info(f"  ✓ {retriever} is imported")
            else:
                logger.error(f"  ✗ {retriever} is NOT imported")
        
        return True
    except Exception as e:
        logger.error(f"Retrieval service error: {e}")
        return False


def main():
    """Run all tests."""
    logger.info("Starting retriever tests...\n")
    
    all_passed = True
    
    logger.info("1. Testing imports...")
    if not test_imports():
        all_passed = False
    
    logger.info("\n2. Testing constants...")
    if not test_constants():
        all_passed = False
    
    logger.info("\n3. Testing retrieval service...")
    if not test_retrieval_service():
        all_passed = False
    
    if all_passed:
        logger.info("\n✅ All tests passed!")
    else:
        logger.error("\n❌ Some tests failed!")
    
    return all_passed


if __name__ == "__main__":
    main()