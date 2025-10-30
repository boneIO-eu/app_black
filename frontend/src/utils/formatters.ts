export const formatTimestamp = (timestamp?: number | null) => {
  if (!timestamp) return 'No timestamp available'; 
  try {
    if (timestamp === 0) return 'No updates yet';
    const date = new Date(timestamp * 1000); // Convert Unix timestamp to milliseconds
    return date.toLocaleTimeString();
  } catch (error) {
    console.error('Error formatting timestamp:', error);
    return 'Invalid timestamp';
  }
};
