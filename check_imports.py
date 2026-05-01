"""检查 LangChain 导入路径"""
import sys

tests = [
    # MultiQueryRetriever
    ("from langchain.retrievers import MultiQueryRetriever", "MultiQueryRetriever"),
    ("from langchain_community.retrievers import MultiQueryRetriever", "MultiQueryRetriever (community)"),
    ("from langchain_community.retrievers.multi_query import MultiQueryRetriever", "MultiQueryRetriever (multi_query)"),

    # EnsembleRetriever
    ("from langchain.retrievers import EnsembleRetriever", "EnsembleRetriever"),
    ("from langchain_community.retrievers import EnsembleRetriever", "EnsembleRetriever (community)"),
    ("from langchain.retrievers.ensemble import EnsembleRetriever", "EnsembleRetriever (ensemble)"),

    # ContextualCompressionRetriever
    ("from langchain.retrievers import ContextualCompressionRetriever", "ContextualCompressionRetriever"),
    ("from langchain.retrievers.contextual_compression import ContextualCompressionRetriever", "ContextualCompressionRetriever (contextual_compression)"),
    ("from langchain_community.retrievers import ContextualCompressionRetriever", "ContextualCompressionRetriever (community)"),

    # CrossEncoderReranker
    ("from langchain.retrievers.document_compressors import CrossEncoderReranker", "CrossEncoderReranker"),
    ("from langchain_community.retrievers.document_compressors import CrossEncoderReranker", "CrossEncoderReranker (community)"),
    ("from langchain_community.retrievers.document_compressors.cross_encoder import CrossEncoderReranker", "CrossEncoderReranker (cross_encoder)"),

    # BM25Retriever
    ("from langchain_community.retrievers.bm25 import BM25Retriever", "BM25Retriever"),
]

with open("check_imports_result.txt", "w", encoding="utf-8") as f:
    f.write("Checking LangChain imports...\n\n")
    found = {}
    for imp, desc in tests:
        try:
            exec(imp)
            f.write(f"OK: {desc}\n")
            found[desc] = imp
        except Exception as e:
            f.write(f"FAIL: {desc}: {type(e).__name__}\n")

    f.write("\n\nAvailable imports:\n")
    for desc, imp in found.items():
        f.write(f"{desc}: {imp}\n")
