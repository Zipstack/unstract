#!/usr/bin/env python3
"""
Streaming Performance Benchmark for Unstract AutoGen Client.

This benchmark tests and measures the performance of streaming vs non-streaming
completions, demonstrating the efficiency gains of streaming for long responses.
"""

import asyncio
import statistics
import time
from collections.abc import Generator
from dataclasses import dataclass
from typing import Any

from autogen_core.models import SystemMessage, UserMessage
from unstract.autogen_client import UnstractAutoGenClient


@dataclass
class BenchmarkResult:
    """Results from a benchmark test."""

    test_name: str
    duration: float
    tokens_generated: int
    tokens_per_second: float
    memory_usage: int
    first_token_latency: float
    streaming: bool


class StreamingBenchmarkAdapter:
    """
    Specialized adapter for streaming benchmarks with configurable response patterns.
    """

    def __init__(self, response_length: str = "medium", delay_per_chunk: float = 0.01):
        self.response_length = response_length
        self.delay_per_chunk = delay_per_chunk
        self.call_count = 0

        # Response templates for different lengths
        self.response_templates = {
            "short": self._generate_short_response,
            "medium": self._generate_medium_response,
            "long": self._generate_long_response,
            "very_long": self._generate_very_long_response,
        }

    def completion(self, messages: list, stream: bool = False, **kwargs: Any) -> Any:
        """Generate completion with optional streaming."""
        self.call_count += 1

        # Get the response generator
        response_func = self.response_templates.get(
            self.response_length, self._generate_medium_response
        )
        full_content = response_func()

        if stream:
            return self._create_streaming_response(full_content)
        else:
            return self._create_regular_response(full_content)

    def _generate_short_response(self) -> str:
        """Generate a short response (~50 tokens)."""
        return """This is a concise response demonstrating the basic functionality of the Unstract AutoGen client.
The integration works smoothly with proper token tracking and error handling."""

    def _generate_medium_response(self) -> str:
        """Generate a medium response (~200 tokens)."""
        return """This is a comprehensive response demonstrating the advanced capabilities of the Unstract AutoGen client integration.
The system effectively bridges Microsoft AutoGen framework with Unstract's LLM adapters, providing seamless interoperability.

Key features include:
- Asynchronous completion handling with proper timeout management
- Comprehensive error handling with specific exception types
- Token usage tracking and reporting for cost management
- Streaming support for real-time response generation
- Retry logic with exponential backoff for reliability
- Full compatibility with AutoGen's agent framework

The implementation follows best practices for production deployments, ensuring robust performance under various load conditions."""

    def _generate_long_response(self) -> str:
        """Generate a long response (~500 tokens)."""
        return """This comprehensive response demonstrates the extensive capabilities and robust architecture of the Unstract AutoGen client integration system.

## Architecture Overview
The Unstract AutoGen client serves as a sophisticated bridge between Microsoft's AutoGen framework and Unstract's powerful LLM adapter ecosystem. This integration enables developers to leverage Unstract's unified adapter interface while maintaining full compatibility with AutoGen's agent-based conversation patterns.

## Core Features
1. **Asynchronous Processing**: Full async/await support ensures non-blocking operations and optimal resource utilization in concurrent environments.

2. **Intelligent Error Handling**: The system implements a comprehensive error handling strategy with specific exception types for different failure modes:
   - Connection errors for network-related issues
   - Timeout errors for request timeouts
   - Validation errors for malformed requests
   - Generic completion errors for adapter-specific failures

3. **Advanced Streaming**: Real-time response streaming with proper chunk handling and final result aggregation.

4. **Usage Analytics**: Detailed token tracking across all requests with separate accounting for prompt and completion tokens.

5. **Reliability Features**: Built-in retry logic with exponential backoff, configurable timeout settings, and graceful degradation.

## Performance Characteristics
The system is optimized for both latency and throughput, with streaming providing significant improvements for long-form content generation. Benchmark testing shows consistent performance across various load patterns."""

    def _generate_very_long_response(self) -> str:
        """Generate a very long response (~1000+ tokens)."""
        return """# Comprehensive Analysis: Unstract AutoGen Client Integration

## Executive Summary
The Unstract AutoGen client represents a significant advancement in LLM integration architecture, providing a robust and scalable solution for enterprise-grade AI applications. This comprehensive analysis covers the technical implementation, performance characteristics, and strategic benefits of the integration.

## Technical Architecture

### Core Components
The integration consists of several key components working in concert:

1. **Client Layer**: The UnstractAutoGenClient class implements the ChatCompletionClient interface, ensuring full compatibility with AutoGen's ecosystem while providing Unstract-specific optimizations.

2. **Adapter Interface**: A clean abstraction layer that allows seamless integration with any Unstract LLM adapter, supporting multiple providers including OpenAI, Anthropic, Azure OpenAI, and others.

3. **Message Processing**: Sophisticated message normalization that handles various input formats while maintaining conversation context and metadata.

4. **Streaming Engine**: Advanced streaming implementation that provides real-time response generation with proper chunk management and final result aggregation.

### Design Patterns
The implementation leverages several important design patterns:

- **Adapter Pattern**: Clean separation between AutoGen interface and Unstract adapter implementation
- **Strategy Pattern**: Configurable retry strategies and error handling approaches
- **Observer Pattern**: Usage tracking and metrics collection throughout the request lifecycle
- **Factory Pattern**: Flexible adapter instantiation and configuration management

## Performance Analysis

### Latency Characteristics
Benchmark testing reveals several key performance insights:

1. **Cold Start**: Initial request latency averages 150-300ms depending on adapter configuration
2. **Warm Requests**: Subsequent requests show 50-100ms latency for standard completions
3. **Streaming Advantage**: First token latency reduced by 60-80% compared to non-streaming requests
4. **Throughput**: Sustained throughput of 500+ requests per second under optimal conditions

### Resource Utilization
The client demonstrates efficient resource usage:
- Memory overhead: <50MB per client instance
- CPU utilization: Minimal overhead during I/O bound operations
- Network efficiency: Optimized request/response handling with connection pooling

## Enterprise Considerations

### Scalability
The architecture supports horizontal scaling with:
- Stateless client design for distributed deployments
- Connection pooling for optimal resource utilization
- Configurable timeout and retry settings for varying load conditions
- Built-in circuit breaker patterns for fault tolerance

### Security
Security features include:
- Secure credential management through Unstract adapter configuration
- Request validation and sanitization
- Audit logging for compliance requirements
- Rate limiting and throttling capabilities

### Monitoring and Observability
Comprehensive monitoring capabilities:
- Detailed usage metrics and token tracking
- Performance monitoring with latency and throughput metrics
- Error tracking and categorization
- Custom metrics integration for business intelligence

## Implementation Best Practices

### Configuration Management
Recommended configuration approaches:
- Environment-based adapter selection
- Centralized timeout and retry configuration
- Dynamic model selection based on task requirements
- Cost optimization through intelligent adapter routing

### Error Handling
Robust error handling strategies:
- Graceful degradation for partial failures
- Intelligent retry logic with exponential backoff
- Circuit breaker implementation for cascading failure prevention
- Comprehensive logging for debugging and analysis

### Performance Optimization
Key optimization techniques:
- Connection pooling for reduced latency
- Intelligent caching strategies where appropriate
- Batch processing for high-volume scenarios
- Streaming for long-form content generation

## Conclusion
The Unstract AutoGen client integration provides a production-ready solution for enterprise AI applications, combining the flexibility of Unstract's adapter ecosystem with the powerful agent framework of AutoGen. The implementation demonstrates excellent performance characteristics, robust error handling, and comprehensive monitoring capabilities suitable for mission-critical deployments."""

    def _create_streaming_response(self, content: str) -> Generator:
        """Create a streaming response with realistic delays."""
        words = content.split()
        chunk_size = 3  # Words per chunk

        def stream_generator():
            for i in range(0, len(words), chunk_size):
                chunk_words = words[i : i + chunk_size]
                chunk_content = (
                    " " + " ".join(chunk_words) if i > 0 else " ".join(chunk_words)
                )

                # Add realistic delay
                time.sleep(self.delay_per_chunk)

                yield self._create_stream_chunk(chunk_content)

        return stream_generator()

    def _create_stream_chunk(self, content: str):
        """Create a streaming chunk object."""

        class StreamChunk:
            def __init__(self, content: str):
                self.choices = [StreamChoice(content)]

        class StreamChoice:
            def __init__(self, content: str):
                self.delta = StreamDelta(content)

        class StreamDelta:
            def __init__(self, content: str):
                self.content = content

        return StreamChunk(content)

    def _create_regular_response(self, content: str):
        """Create a regular (non-streaming) response."""
        # Simulate processing time for full response
        time.sleep(len(content.split()) * self.delay_per_chunk)

        class CompletionResponse:
            def __init__(self, content: str):
                self.choices = [Choice(content)]
                self.usage = Usage(content)
                self.cached = False

        class Choice:
            def __init__(self, content: str):
                self.message = Message(content)
                self.finish_reason = "stop"

        class Message:
            def __init__(self, content: str):
                self.content = content

        class Usage:
            def __init__(self, content: str):
                word_count = len(content.split())
                self.prompt_tokens = 20  # Simulated prompt tokens
                self.completion_tokens = word_count

        return CompletionResponse(content)


class StreamingBenchmark:
    """Comprehensive streaming performance benchmark suite."""

    def __init__(self):
        self.results = []

    async def run_benchmark_suite(self) -> list[BenchmarkResult]:
        """Run comprehensive benchmark suite."""
        print("🚀 Unstract AutoGen Client Streaming Benchmark Suite")
        print("=" * 70)
        print(
            "Testing streaming vs non-streaming performance across different response lengths"
        )
        print()

        # Test configurations
        test_configs = [
            ("Short Response", "short", 0.005),
            ("Medium Response", "medium", 0.008),
            ("Long Response", "long", 0.010),
            ("Very Long Response", "very_long", 0.012),
        ]

        for test_name, length, delay in test_configs:
            print(f"📊 Testing: {test_name}")
            print("-" * 50)

            # Test non-streaming
            non_streaming_result = await self._benchmark_completion(
                f"{test_name} (Non-Streaming)", length, delay, streaming=False
            )
            self.results.append(non_streaming_result)

            # Test streaming
            streaming_result = await self._benchmark_completion(
                f"{test_name} (Streaming)", length, delay, streaming=True
            )
            self.results.append(streaming_result)

            # Compare results
            self._print_comparison(non_streaming_result, streaming_result)
            print()

        # Print overall summary
        self._print_summary()

        return self.results

    async def _benchmark_completion(
        self, test_name: str, response_length: str, delay: float, streaming: bool
    ) -> BenchmarkResult:
        """Benchmark a single completion type."""
        adapter = StreamingBenchmarkAdapter(response_length, delay)
        client = UnstractAutoGenClient(
            llm_adapter=adapter, timeout=60.0, enable_retries=False
        )

        messages = [
            SystemMessage(content="You are a helpful assistant.", source="system"),
            UserMessage(
                content=f"Generate a {response_length} response for benchmarking.",
                source="user",
            ),
        ]

        start_time = time.time()
        first_token_time = None
        tokens_generated = 0
        memory_start = 0  # Simplified for demo

        try:
            if streaming:
                collected_content = []
                async for chunk in client.create_stream(messages):
                    if isinstance(chunk, str):
                        if first_token_time is None:
                            first_token_time = time.time()
                        collected_content.append(chunk)
                        tokens_generated += len(chunk.split())
                    else:
                        # Final result
                        break
            else:
                first_token_time = (
                    time.time()
                )  # For non-streaming, first token is immediate
                result = await client.create(messages)
                tokens_generated = len(result.content.split())
                end_time = time.time()

        except Exception as e:
            print(f"❌ Benchmark failed: {e}")
            return BenchmarkResult(test_name, 0, 0, 0, 0, 0, streaming)

        finally:
            await client.close()

        end_time = time.time()
        duration = end_time - start_time
        first_token_latency = (
            (first_token_time - start_time) if first_token_time else duration
        )
        tokens_per_second = tokens_generated / duration if duration > 0 else 0

        return BenchmarkResult(
            test_name=test_name,
            duration=duration,
            tokens_generated=tokens_generated,
            tokens_per_second=tokens_per_second,
            memory_usage=memory_start,
            first_token_latency=first_token_latency,
            streaming=streaming,
        )

    def _print_comparison(
        self, non_streaming: BenchmarkResult, streaming: BenchmarkResult
    ):
        """Print comparison between streaming and non-streaming results."""
        print("  📈 Non-Streaming:")
        print(f"    ⏱️  Duration: {non_streaming.duration:.3f}s")
        print(f"    🔤 Tokens: {non_streaming.tokens_generated}")
        print(f"    ⚡ Tokens/sec: {non_streaming.tokens_per_second:.1f}")
        print(f"    🚀 First token: {non_streaming.first_token_latency:.3f}s")

        print("  🌊 Streaming:")
        print(f"    ⏱️  Duration: {streaming.duration:.3f}s")
        print(f"    🔤 Tokens: {streaming.tokens_generated}")
        print(f"    ⚡ Tokens/sec: {streaming.tokens_per_second:.1f}")
        print(f"    🚀 First token: {streaming.first_token_latency:.3f}s")

        # Calculate improvements
        if non_streaming.duration > 0:
            duration_improvement = (
                (non_streaming.duration - streaming.duration) / non_streaming.duration
            ) * 100
            throughput_improvement = (
                (streaming.tokens_per_second - non_streaming.tokens_per_second)
                / non_streaming.tokens_per_second
            ) * 100
            first_token_improvement = (
                (non_streaming.first_token_latency - streaming.first_token_latency)
                / non_streaming.first_token_latency
            ) * 100

            print("  📊 Streaming Benefits:")
            print(f"    ⏱️  Duration: {duration_improvement:+.1f}%")
            print(f"    ⚡ Throughput: {throughput_improvement:+.1f}%")
            print(f"    🚀 First token: {first_token_improvement:+.1f}%")

    def _print_summary(self):
        """Print overall benchmark summary."""
        print("=" * 70)
        print("📊 BENCHMARK SUMMARY")
        print("=" * 70)

        streaming_results = [r for r in self.results if r.streaming]
        non_streaming_results = [r for r in self.results if not r.streaming]

        if streaming_results and non_streaming_results:
            avg_streaming_tps = statistics.mean(
                [r.tokens_per_second for r in streaming_results]
            )
            avg_non_streaming_tps = statistics.mean(
                [r.tokens_per_second for r in non_streaming_results]
            )
            avg_streaming_latency = statistics.mean(
                [r.first_token_latency for r in streaming_results]
            )
            avg_non_streaming_latency = statistics.mean(
                [r.first_token_latency for r in non_streaming_results]
            )

            print("📈 Average Performance:")
            print(
                f"  Non-Streaming: {avg_non_streaming_tps:.1f} tokens/sec, {avg_non_streaming_latency:.3f}s first token"
            )
            print(
                f"  Streaming: {avg_streaming_tps:.1f} tokens/sec, {avg_streaming_latency:.3f}s first token"
            )

            overall_throughput_improvement = (
                (avg_streaming_tps - avg_non_streaming_tps) / avg_non_streaming_tps
            ) * 100
            overall_latency_improvement = (
                (avg_non_streaming_latency - avg_streaming_latency)
                / avg_non_streaming_latency
            ) * 100

            print("\n🎯 Overall Streaming Benefits:")
            print(
                f"  ⚡ Throughput improvement: +{overall_throughput_improvement:.1f}%"
            )
            print(
                f"  🚀 First token latency improvement: +{overall_latency_improvement:.1f}%"
            )

        print(f"\n✅ Benchmark completed: {len(self.results)} tests")

        # Recommendations
        print("\n💡 Recommendations:")
        if streaming_results:
            best_streaming = max(streaming_results, key=lambda r: r.tokens_per_second)
            print(f"  🏆 Best streaming performance: {best_streaming.test_name}")
            print(f"      {best_streaming.tokens_per_second:.1f} tokens/sec")

        print(
            "  📝 Use streaming for responses > 100 tokens for better user experience"
        )
        print("  ⚡ Use non-streaming for short responses < 50 tokens")
        print("  🔄 Consider caching for frequently requested content")


async def main():
    """Run the streaming benchmark demonstration."""
    benchmark = StreamingBenchmark()
    results = await benchmark.run_benchmark_suite()

    print("\n🎉 Streaming benchmark completed successfully!")
    print(f"📊 Total tests: {len(results)}")

    return len(results) > 0


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)
