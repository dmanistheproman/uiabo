"""Direct claim-to-web-research path, isolated from the legacy retrieval stages."""

import asyncio
from datetime import datetime, timedelta, timezone
import time
from uuid import uuid4

from pydantic import ValidationError

from app.pipeline.evidence_assessment.openai_provider import get_settings, OpenAIProviderError
from app.pipeline.input_preparation.service import prepare_text
from app.pipeline.shared.errors import (
    PipelineComponentError, PipelineContractError, PipelineError, PipelineValidationError,
)
from app.pipeline.shared.models import (
    FailedAnalysisRecord, PreparedText, RetrievalTrace, provider_transport_diagnostics,
)
from app.pipeline.shared.runtime_budget import request_budget


class OpenAIResearchPipeline:
    """Keep the authenticated route's storage, quota and monitoring boundary."""

    def __init__(self, *, repository, run_recorder=None, prepare_input=prepare_text,
                 researcher=None, clock=None, id_factory=None, pipeline_version=None):
        if researcher is None:
            from app.pipeline.evidence_assessment.openai_research import research_claim
            researcher = research_claim
        if pipeline_version is None:
            try:
                settings = get_settings()
            except OpenAIProviderError as error:
                raise PipelineComponentError(error.message, error_code=error.code,
                    stage='evidence_assessment', retryable=error.retryable) from None
            pipeline_version = f'openai-web-v1:{settings.model}:reasoning-{settings.reasoning_effort}:credibility-v2'
        self._repository = repository
        self._run_recorder = run_recorder
        self._prepare_input = prepare_input
        self._researcher = researcher
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._id_factory = id_factory or (lambda: str(uuid4()))
        self._pipeline_version = pipeline_version

    @property
    def pipeline_version(self):
        return self._pipeline_version

    def with_repository(self, repository, *, id_factory=None, run_recorder=None):
        return OpenAIResearchPipeline(repository=repository,
            run_recorder=self._run_recorder if run_recorder is None else run_recorder,
            prepare_input=self._prepare_input, researcher=self._researcher,
            clock=self._clock, id_factory=id_factory, pipeline_version=self.pipeline_version)

    def _record_run_best_effort(self, run):
        if self._run_recorder:
            try:
                self._run_recorder(run)
            except Exception:
                pass

    def _prepare(self, text):
        try:
            raw = self._prepare_input(text)
            return PreparedText.model_validate(raw.model_dump() if hasattr(raw, 'model_dump') else raw)
        except PipelineError:
            raise
        except Exception as error:
            if all(hasattr(error, name) for name in ('message', 'error_code', 'http_status')):
                raise PipelineValidationError(str(error.message), error_code=str(error.error_code),
                    http_status=int(error.http_status)) from None
            raise PipelineComponentError('Input preparation could not be completed.',
                error_code='INPUT_PREPARATION_FAILED', stage='input_preparation') from None

    def analyze(self, text):
        from app.pipeline.evidence_assessment.research_result import build_research_result
        result_id, created_at = self._id_factory(), self._clock()
        started = time.perf_counter()
        prepared, timings = None, {}
        trace = RetrievalTrace()
        base_run = dict(run_id=result_id, input_type='text', created_at=created_at,
                        pipeline_version=self.pipeline_version)
        try:
            with request_budget():
                stage_start = time.perf_counter()
                prepared = self._prepare(text)
                timings['input_preparation'] = int((time.perf_counter() - stage_start) * 1000)
                stage_start = time.perf_counter()
                try:
                    research = asyncio.run(self._researcher(prepared.original_text,
                        as_of=created_at.astimezone(timezone(timedelta(hours=8))).date(), trace=trace))
                except PipelineError:
                    raise
                except Exception:
                    raise PipelineComponentError('OpenAI web research could not be completed.',
                        error_code='OPENAI_RESEARCH_FAILED', stage='evidence_assessment') from None
                finally:
                    timings['web_research'] = int((time.perf_counter() - stage_start) * 1000)
                try:
                    result = build_research_result(prepared=prepared, research=research,
                        result_id=result_id, created_at=created_at,
                        pipeline_version=self.pipeline_version, trace=trace)
                except (ValidationError, ValueError, TypeError, AttributeError):
                    raise PipelineContractError('The web research result did not pass validation.',
                        stage='result_assembly') from None
                self._repository.save_result(result)
            self._record_run_best_effort({**base_run, 'status': 'completed',
                'finished_at': self._clock(), 'duration_ms': int((time.perf_counter() - started) * 1000),
                'stage_timings_ms': timings,
                'provider_diagnostics': [event.model_dump(mode='json', exclude_none=True)
                                         for event in provider_transport_diagnostics(trace)]})
            return result
        except PipelineError as error:
            diagnostics = provider_transport_diagnostics(trace)
            self._record_run_best_effort({**base_run, 'status': 'failed',
                'finished_at': self._clock(), 'duration_ms': int((time.perf_counter() - started) * 1000),
                'stage_timings_ms': timings, 'failure_stage': error.stage,
                'error_code': error.error_code, 'message': error.message,
                'provider_diagnostics': [event.model_dump(mode='json', exclude_none=True)
                                         for event in diagnostics]})
            if prepared is not None:
                try:
                    self._repository.save_failure(FailedAnalysisRecord(result_id=result_id,
                        original_text=prepared.original_text, failure_stage=error.stage,
                        error_code=error.error_code, message=error.message, retryable=error.retryable,
                        provider_diagnostics=diagnostics,
                        pipeline_version=self.pipeline_version, warnings=prepared.warnings, created_at=created_at))
                except Exception:
                    pass
            raise
