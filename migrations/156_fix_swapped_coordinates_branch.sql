-- Fix swapped coordinates in branch table where lat > 100 and lng < 100
UPDATE public.branch
SET 
  lat = lng, 
  lng = lat
WHERE lat > 100 AND lng < 100 AND lat IS NOT NULL AND lng IS NOT NULL;
