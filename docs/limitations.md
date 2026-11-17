# Limitations

- **Comprehension is unverified.** Real inference has not run; no key was available. Every semantic output
  produced so far comes from hand-authored fixtures, which are labelled as fixtures.
- **Fixture checks are engineering checks.** The 15/15 pass rate shows that contracts, validators and
  rendering behave as designed. The fixture answers were written by the implementer, so it says nothing about understanding.
- **Human evaluation has not run.** The annotation guide, Label Studio config, pairwise packets and agreement
  statistics are built, but no annotations exist yet.
- **Style classifier scope.** It covers one dataset's five labels, uses TF-IDF features and has a small test
  set (202 texts, 35 to 49 per class). The hierarchical variant's gain is within noise. The neutral class may
  be separated partly by register.
- **Guards are pattern-based.** The modality and psychological-claim guards use regular expressions. They catch
  common phrasings, not every paraphrase. Human review of unsupported claims remains part of the protocol.
- **Lexical retrieval** has not yet been shown to beat the no-retrieval baseline. That needs the live run.
- **Profiles** are descriptive rule fits from explicit feedback. Predictive performance is unmeasured until enough
  timestamped feedback exists for a temporal holdout.
- **Multimodal.** Only text and transcripts read as text are processed. A transcript cannot establish vocal
  sarcasm or deadpan delivery. Image, audio and video return `unsupported`.
- **Synthetic counterfactual edits** are not enabled. Only caller-supplied variants are compared, and an
  observed change still needs human validation.
- **Languages.** The ontology, prompts and fixtures are English. Other languages are untested.
