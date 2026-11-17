# Annotation guide (pilot v1)

Annotate each item **independently**. Do not discuss items until adjudication.

1. **Comic reading.** Is a humorous reading supported by the text and its supplied context?
   - `supported`: you can say what creates the humour, pointing at the words.
   - `not_supported`: it reads as sincere or literal. Informal tone, "lol" or a mention of committees does not make text a joke.
   - `ambiguous`: a literal and a comic reading are both credible.
   - `insufficient_context`: the reading depends on something not supplied, such as an earlier turn or a shared event.
2. **Mechanisms and modes.** Tick all that apply. A dark subject alone is not aggression. A word with two dictionary
   meanings is not a pun unless the text activates both.
3. **Evidence.** Highlight the exact words that carry the reading: the setup that builds an expectation and the trigger that changes it.
4. **Essential elements.** List what any correct explanation must mention, such as "'interest' as money and as attention".
   Several acceptable readings are allowed; list each.
5. **Unsupported claims.** When later judging explanations, mark any claim about tone of voice, intent,
   personality or context that the input does not support.
6. **Audience fit** is a separate question from 1. Answer `no_audience_stated` when there is no stated audience.

Examples are in `knowledge/patterns/cards.yaml` (positive, negative and borderline cases for each pattern).
Quoted speech belongs to its quoted voice, not the narrator. A callback needs its antecedent; if the antecedent
is missing, the answer is `insufficient_context` or `not_supported`.
