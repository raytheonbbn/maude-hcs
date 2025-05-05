from Maude.attack_exploration.src.zone import Record

class ResolverCache:

    def __init__(self, name, entries) -> None:
        self.name = name        
        self.entries = entries    

    # op rsvCache : -> Cache .
    def to_maude(self):
        assert self.entries, "Cache has no records"
        
        res = f'op {self.name} : -> Cache .\n'
        res += f'eq {self.name} ='
        for record in self.entries:
            res += f'\n  {record.to_maude()}'
        res += ' .'
        return res
    
class CacheEntry():
    def __init__(self, record : Record, cred : int = 1):
        self.record = record
        self.cred = cred
    
    # cacheEntry(< 'com . root, ns, testTTL, 'ns . 'com . root >, 1)
    def to_maude(self):
        return f"cacheEntry({self.record.to_maude()}, {self.cred})"
        