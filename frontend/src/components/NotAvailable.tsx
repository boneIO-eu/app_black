import { useAppInit } from "@/contexts/AppInitContext";

const NotAvailable = () => {
    const { isLoading, refetch } = useAppInit();

    return (<div className="fixed inset-0 flex items-center justify-center z-50">
        <div className="p-8 text-center">
          <div className="loading loading-dots loading-lg mb-4"></div>
          <h2 className="text-xl font-bold mb-4">
            API unavailable
          </h2>
          <p className="text-base-content/70 mb-4">
            {isLoading
              ? 'Checking if service is back online...'
              : 'Service appears to be offline.'}
          </p>
          <button 
            onClick={refetch} 
            disabled={isLoading}
            className="btn btn-primary"
          >
            {isLoading ? 'Checking...' : 'Check Now'}
          </button>
        </div>
      </div>)
}

export default NotAvailable