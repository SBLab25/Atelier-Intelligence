import { useEffect } from 'react';

export function useCJITracker() {
    useEffect(() => {
        if (typeof window !== 'undefined' && !window.CJI_CONFIG) {
            window.CJI_CONFIG = {
                api_key: "YOUR_TRACKER_API_KEY",
                journey_name: "my_vercel_site",
                collector_url: "https://tcs-cjipip-install-r-cji-agent.onrender.com/collect/batch"
            };

            const script = document.createElement('script');
            script.src = "https://tcs-cjipip-install-r-cji-agent.onrender.com/tracker.js";
            script.defer = true;
            document.head.appendChild(script);
        }
    }, []);
}