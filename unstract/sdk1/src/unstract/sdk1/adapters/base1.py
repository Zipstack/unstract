class BaseParameters(BaseModel):
    """ Base parameters for all LLM providers.
        See https://docs.litellm.ai/docs/completion/input#input-params-1
    """
    model: str
    # The sampling temperature to be used, between 0 and 2.
    temperature: Optional[float] = Field(default=0.1, ge=0, le=2)
    # The number of chat completion choices to generate for each input message.
    n: Optional[int] = 1
    timeout: Optional[Union[float, int]] = 600
    stream: Optional[bool] = False
    max_tokens: Optional[int] = None
    num_retries: Optional[int] = None