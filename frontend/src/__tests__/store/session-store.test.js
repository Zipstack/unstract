/**
 * Tests for session-store.js
 * Tier 1: Critical path - authentication state management
 */
import { act, renderHook } from '@testing-library/react';
import { useSessionStore } from '../../store/session-store';

describe('useSessionStore', () => {
  // Reset store state before each test
  beforeEach(() => {
    const { result } = renderHook(() => useSessionStore());
    act(() => {
      result.current.setSessionDetails({});
      result.current.setLogoutLoading(false);
    });
  });

  describe('initial state', () => {
    it('should have empty sessionDetails initially', () => {
      const { result } = renderHook(() => useSessionStore());
      expect(result.current.sessionDetails).toEqual({});
    });

    it('should have isLogoutLoading as false initially', () => {
      const { result } = renderHook(() => useSessionStore());
      expect(result.current.isLogoutLoading).toBe(false);
    });
  });

  describe('setSessionDetails', () => {
    it('should set session details correctly', () => {
      const { result } = renderHook(() => useSessionStore());
      const mockDetails = {
        isLoggedIn: true,
        orgName: 'test-org',
        role: 'admin',
      };

      act(() => {
        result.current.setSessionDetails(mockDetails);
      });

      expect(result.current.sessionDetails).toEqual(mockDetails);
    });

    it('should replace all session details when called', () => {
      const { result } = renderHook(() => useSessionStore());

      act(() => {
        result.current.setSessionDetails({ isLoggedIn: true, orgName: 'org1' });
      });

      act(() => {
        result.current.setSessionDetails({ isLoggedIn: false });
      });

      // Should completely replace, not merge
      expect(result.current.sessionDetails).toEqual({ isLoggedIn: false });
      expect(result.current.sessionDetails.orgName).toBeUndefined();
    });
  });

  describe('updateSessionDetails', () => {
    it('should merge new details with existing details', () => {
      const { result } = renderHook(() => useSessionStore());

      act(() => {
        result.current.setSessionDetails({
          isLoggedIn: true,
          orgName: 'test-org',
        });
      });

      act(() => {
        result.current.updateSessionDetails({ role: 'admin' });
      });

      expect(result.current.sessionDetails).toEqual({
        isLoggedIn: true,
        orgName: 'test-org',
        role: 'admin',
      });
    });

    it('should overwrite existing properties when updating', () => {
      const { result } = renderHook(() => useSessionStore());

      act(() => {
        result.current.setSessionDetails({
          isLoggedIn: true,
          orgName: 'old-org',
        });
      });

      act(() => {
        result.current.updateSessionDetails({ orgName: 'new-org' });
      });

      expect(result.current.sessionDetails.orgName).toBe('new-org');
      expect(result.current.sessionDetails.isLoggedIn).toBe(true);
    });
  });

  describe('setLogoutLoading', () => {
    it('should set logout loading state to true', () => {
      const { result } = renderHook(() => useSessionStore());

      act(() => {
        result.current.setLogoutLoading(true);
      });

      expect(result.current.isLogoutLoading).toBe(true);
    });

    it('should set logout loading state to false', () => {
      const { result } = renderHook(() => useSessionStore());

      act(() => {
        result.current.setLogoutLoading(true);
      });

      act(() => {
        result.current.setLogoutLoading(false);
      });

      expect(result.current.isLogoutLoading).toBe(false);
    });
  });

  describe('state persistence across hook instances', () => {
    it('should share state between multiple hook instances', () => {
      const { result: result1 } = renderHook(() => useSessionStore());
      const { result: result2 } = renderHook(() => useSessionStore());

      act(() => {
        result1.current.setSessionDetails({ isLoggedIn: true });
      });

      // Second instance should see the updated state
      expect(result2.current.sessionDetails).toEqual({ isLoggedIn: true });
    });
  });
});
