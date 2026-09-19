"use client";

import { useEffect, useState } from "react";
import {
	AUTH_EXPIRED_EVENT,
	clearAuthToken,
	getAuthToken,
	setAuthToken,
} from "../lib/auth";

export function useAuth() {
	const [token, setTokenState] = useState("");
	const [ready, setReady] = useState(false);

	useEffect(() => {
		setTokenState(getAuthToken());
		setReady(true);

		const handleAuthExpired = () => setTokenState("");
		window.addEventListener(AUTH_EXPIRED_EVENT, handleAuthExpired);
		return () => window.removeEventListener(AUTH_EXPIRED_EVENT, handleAuthExpired);
	}, []);

	const updateToken = (nextToken: string) => {
		setAuthToken(nextToken);
		setTokenState(nextToken);
	};

	const removeToken = () => {
		clearAuthToken();
		setTokenState("");
	};

	return {
		token,
		ready,
		setToken: updateToken,
		clearToken: removeToken,
	};
}
