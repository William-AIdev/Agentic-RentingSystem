insert into catalog (sku, color, size) values
('BLACK_S','black','S'),('BLACK_M','black','M'),('BLACK_L','black','L'),
('WHITE_S','white','S'),('WHITE_M','white','M'),('WHITE_L','white','L')
on conflict (sku) do nothing;
