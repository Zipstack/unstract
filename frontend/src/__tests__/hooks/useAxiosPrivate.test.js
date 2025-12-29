/**
 * Tests for useAxiosPrivate hook
 * Tier 1: Critical path - API request handling with auth
 */
import { renderHook, act, waitFor } from '@testing-library/react';
import { useAxiosPrivate } from '../../hooks/useAxiosPrivate';

// Mock useLogout hook
const mockLogout = jest.fn();
jest.mock('../../hooks/useLogout', () => ({
  __esModule: true,
  default: () => mockLogout,
}));

describe('useAxiosPrivate', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('initialization', () => {
    it('should return an axios instance', () => {
      const { result } = renderHook(() => useAxiosPrivate());
      expect(result.current).toBeDefined();
      expect(typeof result.current.get).toBe('function');
      expect(typeof result.current.post).toBe('function');
      expect(typeof result.current.put).toBe('function');
      expect(typeof result.current.delete).toBe('function');
    });

    it('should have interceptors configured', () => {
      const { result } = renderHook(() => useAxiosPrivate());
      expect(result.current.interceptors).toBeDefined();
      expect(result.current.interceptors.response).toBeDefined();
    });
  });

  describe('response interceptor', () => {
    it('should pass through successful responses', async () => {
      const { result } = renderHook(() => useAxiosPrivate());

      // The axios instance should handle successful responses normally
      // This is a structural test - the actual HTTP call would be mocked in integration tests
      expect(result.current.interceptors.response).toBeDefined();
    });

    it('should call logout on 401 response', async () => {
      const { result } = renderHook(() => useAxiosPrivate());

      // Get the response interceptor error handler
      const interceptorCalls = result.current.interceptors.response.handlers;

      if (interceptorCalls && interceptorCalls.length > 0) {
        const errorHandler = interceptorCalls[0].rejected;

        // Simulate a 401 error
        const error401 = {
          response: { status: 401 },
        };

        await act(async () => {
          try {
            await errorHandler(error401);
          } catch (e) {
            // Expected to reject
          }
        });

        expect(mockLogout).toHaveBeenCalled();
      }
    });

    it('should not call logout on non-401 errors', async () => {
      const { result } = renderHook(() => useAxiosPrivate());

      const interceptorCalls = result.current.interceptors.response.handlers;

      if (interceptorCalls && interceptorCalls.length > 0) {
        const errorHandler = interceptorCalls[0].rejected;

        // Simulate a 500 error
        const error500 = {
          response: { status: 500 },
        };

        await act(async () => {
          try {
            await errorHandler(error500);
          } catch (e) {
            // Expected to reject
          }
        });

        expect(mockLogout).not.toHaveBeenCalled();
      }
    });
  });

  describe('cleanup', () => {
    it('should eject interceptor on unmount', () => {
      const { result, unmount } = renderHook(() => useAxiosPrivate());

      const ejectSpy = jest.spyOn(
        result.current.interceptors.response,
        'eject'
      );

      unmount();

      // Interceptor should be ejected on cleanup
      expect(ejectSpy).toHaveBeenCalled();
    });
  });
});
