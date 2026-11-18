const WORKFLOW_TEMPLATES = {
  role_pipeline: {
    defaultName: 'Duo Architect & Coder',
    defaultSlug: 'duo_architect_coder',
    members: [
      {
        role: 'architect',
        provHint: 'coarena',
        modelHint: 'gemini-4-carbon',
        tokens: '',
        mode: 'normal',
        recommended: 'normal',
        prompt: 'You are the Lead Software Architect. Formulate a structured blueprint. Be concise, output a structured blueprint only without filler text.'
      },
      {
        role: 'coder',
        provHint: 'groq',
        modelHint: 'openai/gpt-oss-120b',
        tokens: '',
        mode: 'agentic',
        recommended: 'agentic',
        prompt: 'You are the Senior Implementation Engineer. Execute the approved architectural plan with clean, complete code and necessary tool calls.'
      }
    ]
  },
  parallel_council: {
    defaultName: 'Supreme Judge Consensus',
    defaultSlug: 'supreme_judge_council',
    members: [
      {
        role: 'councilor_1',
        provHint: 'coarena',
        modelHint: 'gemini-4-carbon',
        tokens: '',
        mode: 'normal',
        recommended: 'normal',
        prompt: 'Expert perspective 1: Deep reasoning & architectural rigor. Be concise, output a structured blueprint only without filler text.'
      },
      {
        role: 'councilor_2',
        provHint: 'groq',
        modelHint: 'openai/gpt-oss-120b',
        tokens: '',
        mode: 'normal',
        recommended: 'normal',
        prompt: 'Expert perspective 2: Fast pragmatic engineering, algorithm optimization, and edge-case prevention.'
      },
      {
        role: 'judge',
        provHint: 'googlestudio',
        modelHint: 'models/gemini-3.5-flash-lite',
        tokens: '',
        mode: 'agentic',
        recommended: 'agentic',
        prompt: 'You are Supreme Judge and Synthesizer. Review all candidate solutions above, eliminate discrepancies, combine strengths, and deliver the final authoritative, bug-free solution.'
      }
    ]
  },
  plan_execute_audit: {
    defaultName: 'Full Cycle Tri-Tier Team',
    defaultSlug: 'full_cycle_team',
    members: [
      {
        role: 'architect',
        provHint: 'coarena',
        modelHint: 'gemini-4-carbon',
        tokens: '',
        mode: 'normal',
        recommended: 'normal',
        prompt: 'System Architect: Analyze requirements, outline components and safety invariants. Be concise, output a structured blueprint only without filler text.'
      },
      {
        role: 'builder',
        provHint: 'groq',
        modelHint: 'openai/gpt-oss-120b',
        tokens: '',
        mode: 'agentic',
        recommended: 'agentic',
        prompt: 'Lead Builder: Implement complete, functional code following the architectural plan.'
      },
      {
        role: 'auditor',
        provHint: 'googlestudio',
        modelHint: 'models/gemini-3.5-flash-lite',
        tokens: '',
        mode: 'agentic',
        recommended: 'agentic',
        prompt: 'Security & Quality Auditor: Rigorously audit the built code for edge cases, security flaws, and performance regressions; output the final verified version.'
      }
    ]
  },
  speculative_draft: {
    defaultName: 'Speculative Lightning Draft',
    defaultSlug: 'speculative_draft_team',
    members: [
      {
        role: 'fast_drafter',
        provHint: 'googlestudio',
        modelHint: 'models/gemini-3.5-flash-lite',
        tokens: '',
        mode: 'normal',
        recommended: 'normal',
        prompt: 'Rapid Prototyper: Generate an immediate structural scaffold and pseudocode. Be concise, output a structured blueprint only without filler text.'
      },
      {
        role: 'deep_finisher',
        provHint: 'coarena',
        modelHint: 'gemini-4-carbon',
        tokens: '',
        mode: 'agentic',
        recommended: 'agentic',
        prompt: 'Deep Reasoning Finisher: Take the rapid draft, complete all implementations, enforce production hardening, and produce the final polished response.'
      }
    ]
  },
  router_evaluator: {
    defaultName: 'Smart Dynamic Router Team',
    defaultSlug: 'dynamic_router_team',
    members: [
      {
        role: 'gatekeeper',
        provHint: 'googlestudio',
        modelHint: 'models/gemini-3.5-flash-lite',
        tokens: '',
        mode: 'normal',
        recommended: 'normal',
        prompt: 'Complexity Gatekeeper: Classify user query complexity (1-10) and outline requirements. Be concise, output a structured blueprint only without filler text.'
      },
      {
        role: 'expert',
        provHint: 'groq',
        modelHint: 'openai/gpt-oss-120b',
        tokens: '',
        mode: 'agentic',
        recommended: 'agentic',
        prompt: 'Domain Specialist: Deliver the complete authoritative solution tailored to the evaluated complexity.'
      }
    ]
  },
  worker_reviewer: {
    defaultName: 'Worker & Polisher Team',
    defaultSlug: 'worker_reviewer_team',
    members: [
      {
        role: 'worker',
        provHint: 'groq',
        modelHint: 'openai/gpt-oss-120b',
        tokens: '',
        mode: 'normal',
        recommended: 'normal',
        prompt: 'Primary Worker: Draft initial complete response. Be concise, output a structured blueprint only without filler text.'
      },
      {
        role: 'reviewer',
        provHint: 'coarena',
        modelHint: 'gemini-4-carbon',
        tokens: '',
        mode: 'agentic',
        recommended: 'agentic',
        prompt: 'Senior Reviewer: Polish wording, correct any technical inaccuracies, and present the final refined answer.'
      }
    ]
  }
};

