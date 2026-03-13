# devhelper/reflection_retry.py

def re_reflect_if_needed(reflection, refined_text, run_agent_3_fn, threshold=0.5):
    score = reflection.get("reflection_score", 0.0)
    if score < threshold:
        print(f"[RETRY] Low reflection_score={score:.2f} < threshold={threshold:.2f} → re-running Agent 3...")
        try:
            retry = run_agent_3_fn(refined_text)
            retry["re_reflected"] = True
            return retry
        except Exception as e:
            print(f"❌ Agent_3 retry failed: {e}")
            reflection["re_reflected"] = False  # fallback
            return reflection
    else:
        reflection["re_reflected"] = False
        return reflection