from Maude.attack_exploration.src.config import Config

class MaudeHCSMaudeEncoder(object):

    def __init__(self) -> None:
        pass

    def encode(self, o):
        if not isinstance(o, Config):
            raise Exception(f'can only encode business process objects in Maude. got {type(o)} instead')
        return self.generate_maude(o)
    
    def generate_maude(self, o):
        return o.to_maude_nondet({})


class MaudeHCSEncoder(object):
    def __init__(self, format='maude'):
        self.format = format        
        if format == 'maude':
            self.encoder = MaudeHCSMaudeEncoder()
        else:
            raise Exception(f'Unknown serialization format {format}')


    def encode(self, o):
        return self.encoder.encode(o)