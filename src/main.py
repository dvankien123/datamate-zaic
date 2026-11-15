"""Main CLI entrypoint for DataMate pipeline and evaluation."""
import os
import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import json
import time
import argparse
from tqdm import tqdm

from src.agent.generator import DataMateAgent
from src.llm.client import LocalLLMClient
from src.evaluation.metric import calculate_penalized_accuracy


def load_jsonl(file_path: str):
    data = []
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                data.append(json.loads(line.strip()))
    return data


def save_jsonl(data, file_path: str):
    Path(file_path).parent.mkdir(parents=True, exist_ok=True)
    with open(file_path, "w", encoding="utf-8") as f:
        for item in data:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")


def main():
    parser = argparse.ArgumentParser(description="DataMate Agent Runner & Evaluator")
    parser.add_argument("--mode", type=str, choices=["run", "eval"], default="run", help="Mode: run inference or evaluate")
    parser.add_argument("--data-dir", type=str, default="data/public_test", help="Path to data split directory")
    parser.add_argument("--output", type=str, default="submission.jsonl", help="Output path for submission.jsonl")
    parser.add_argument("--sample-size", type=int, default=None, help="Run on first N questions")
    parser.add_argument("--llm-url", type=str, default="http://localhost:8000/v1", help="Base URL of local LLM")
    parser.add_argument("--model-name", type=str, default="qwen2.5-coder-7b", help="LLM model name")
    
    args = parser.parse_args()
    
    data_dir = Path(args.data_dir)
    questions_file = data_dir / "questions.jsonl"
    answers_file = data_dir / "answers.jsonl" if args.mode == "eval" else None
    calendar_file = data_dir / "calendar.csv"
    
    if not questions_file.exists():
        print(f"Error: {questions_file} not found.")
        sys.exit(1)
        
    questions = load_jsonl(str(questions_file))
    if args.sample_size:
        questions = questions[:args.sample_size]
        
    print(f"Loaded {len(questions)} questions from {questions_file}")
    
    llm_client = LocalLLMClient(base_url=args.llm_url, model_name=args.model_name)
    is_llm_ready = llm_client.is_available()
    print(f"Local LLM Server ({args.llm_url}): {'ONLINE' if is_llm_ready else 'OFFLINE (fallback mode)'}")
    
    agent = DataMateAgent(
        data_dir=str(data_dir),
        calendar_path=str(calendar_file) if calendar_file.exists() else None,
        llm_client=llm_client
    )
    
    predictions = []
    logs = []
    
    print("\nProcessing questions...")
    t_start = time.time()
    
    for q in tqdm(questions):
        t0 = time.time()
        pred = agent.answer_question(q)
        elapsed = time.time() - t0
        
        predictions.append(pred)
        logs.append({
            "id": q["id"],
            "business_id": q["business_id"],
            "question": q["question"],
            "as_of_date": q["as_of_date"],
            "answer": pred,
            "elapsed_seconds": round(elapsed, 3)
        })
        
    agent.close()
    total_time = time.time() - t_start
    print(f"Completed {len(predictions)} questions in {total_time:.2f}s (avg: {total_time/len(predictions):.2f}s/q)")

    # Save predictions and logs, or evaluate if answers are available
    if args.mode == "run":
        # Save submission
        save_jsonl(predictions, args.output)
        print(f"Saved predictions to {args.output}")
        
        # Save logs
        logs_file = Path("logs") / "inference_logs.jsonl"
        save_jsonl(logs, str(logs_file))
        print(f"Saved logs to {logs_file}")
    elif args.mode == "eval" and answers_file.exists():
        references = load_jsonl(str(answers_file))
        if args.sample_size:
            references = references[:args.sample_size]
        eval_res = calculate_penalized_accuracy(predictions, references)
        print("\n" + "=" * 50)
        print("EVALUATION RESULTS (Penalized Accuracy)")
        print("=" * 50)
        print(f"Penalized Accuracy (PA): {eval_res['penalized_accuracy']:.4f}")
        print(f"Total Questions:         {eval_res['total']}")
        print(f"Correct Answers (+1):    {eval_res['correct']}")
        print(f"Wrong Answers   (-1):    {eval_res['wrong']}")
        print(f"Abstain Answers ( 0):    {eval_res['abstain']}")
        print("=" * 50)


if __name__ == "__main__":
    main()
