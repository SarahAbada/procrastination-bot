from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import HuggingFaceEmbeddings

import requests

def download_pdf(url, filename):
    response = requests.get(url)
    with open(filename, 'wb') as f:
        f.write(response.content)
    return filename

def lecture_source(lecture_path):
    loader = PyPDFLoader(lecture_path)
    pages = loader.load()
    print(f"Loaded {len(pages)} pages")

    splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
    chunks = splitter.split_documents(pages)
    print(f"Created {len(chunks)} chunks")

    embeddings = HuggingFaceEmbeddings()
    vectorstore = FAISS.from_documents(chunks, embeddings)
    return vectorstore

def process_assignment(assignment, lecture_path):
    vectorstore = lecture_source(lecture_path)

    pdf_path = download_pdf(assignment["link"], "assignment.pdf")
    assignment_loader = PyPDFLoader(pdf_path)
    assignment_pages = assignment_loader.load()
    assignment_text = " ".join([p.page_content for p in assignment_pages])

    relevant_chunks = vectorstore.similarity_search(assignment_text, k=3)
    relevant_content = " ".join([c.page_content for c in relevant_chunks])

    return {
        "title": assignment["title"],
        "due": assignment["due"],
        "assignment_text": assignment_text,
        "relevant_lecture_content": relevant_content
    }
