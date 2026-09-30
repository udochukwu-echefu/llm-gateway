from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, model_validator

ProviderName = Literal["openai", "groq", "gemini", "deepseek", "zai", "nvidia"]


class RequestModel(BaseModel):
    """Base for everything a client sends.

    Unknown fields and loose types ("0.2" for a number) are rejected, so a typo like
    `temprature` fails loudly instead of being silently ignored.
    """

    model_config = ConfigDict(extra="forbid", strict=True, serialize_by_alias=True)


class ResponseModel(BaseModel):
    """Base for everything a provider sends back.

    Tolerant on purpose: providers add fields over time, and a new one must not break
    traffic. Unknown fields are kept and passed on to the client.
    """

    model_config = ConfigDict(extra="allow", serialize_by_alias=True)


class ZeroOmittingResponseModel(ResponseModel):
    """Restore declared numeric zeros omitted by protobuf JSON, including on output."""

    @model_validator(mode="after")
    def _materialize_zero_defaults(self) -> Self:
        for name, field in type(self).model_fields.items():
            if (
                type(field.default) is int
                and field.default == 0
                and name not in self.model_fields_set
            ):
                # Assignment marks the field as set so exclude_unset=True preserves it.
                setattr(self, name, 0)
        return self


class ProxiedRequest(RequestModel):
    """A request the gateway forwards to a provider.

    Options that exist on only one provider go in `provider_options`, keyed by provider.
    Only the options for the provider that serves the request are sent, so a request can
    later fall back to another provider without breaking. See docs/adr/0003.
    """

    provider_options: dict[ProviderName, dict[str, Any]] | None = None

    @model_validator(mode="after")
    def _provider_options_cannot_override_canonical_fields(self) -> Self:
        canonical = {field.alias or name for name, field in type(self).model_fields.items()}
        for provider, options in (self.provider_options or {}).items():
            clashes = sorted(canonical & options.keys())
            if clashes:
                # Otherwise provider_options could bypass checks that read the canonical
                # fields, such as a future max_tokens cap or guardrails on `messages`.
                raise ValueError(
                    f"provider_options.{provider} cannot set standard fields: {', '.join(clashes)}"
                )
        return self

    def to_upstream(self, provider: ProviderName) -> dict[str, Any]:
        """The body to send to `provider`: what the client set, plus that provider's options."""
        payload = self.model_dump(mode="json", exclude_unset=True, exclude={"provider_options"})
        payload.update((self.provider_options or {}).get(provider, {}))
        return payload
