# -*- coding: UTF-8 -*-
from __future__ import division
import sys, time, os, cPickle
sys.path.append('..')
import dynet as dy
import numpy as np
import models
from lib import Vocab, DataLoader, MixedDataLoader
from test import test
from config import Configurable
import argparse
if __name__ == "__main__":
	np.random.seed(666)
	argparser = argparse.ArgumentParser()
	argparser.add_argument('--config_file', default='../configs/sent.cfg')
	argparser.add_argument('--in_domain_file', default='../../sancl_data/gweb-emails-dev.conll')
	argparser.add_argument('--model', default='SentParser')
	argparser.add_argument('--baseline_path', default='../ckpt/sota')
	argparser.add_argument('--domain_loss_scale', type=float, default = 0.)

	args, extra_args = argparser.parse_known_args()
	config = Configurable(args.config_file, extra_args)
	Parser = getattr(models, args.model)

	vocab = cPickle.load(open(os.path.join(args.baseline_path,'vocab')))
	cPickle.dump(vocab, open(config.save_vocab_path, 'w'))
	if args.model == 'BaseParser':
		parser = Parser(vocab, config.word_dims, config.tag_dims, config.dropout_emb, config.lstm_layers, config.lstm_hiddens, config.dropout_lstm_input, config.dropout_lstm_hidden, config.mlp_arc_size, config.mlp_rel_size, config.dropout_mlp)
		parser.load(os.path.join(args.baseline_path,'model'))
		pc = parser.parameter_collection
	elif args.model == 'SentParser':
		parser = Parser(vocab, config.word_dims, config.tag_dims, config.dropout_emb, config.lstm_layers, config.lstm_hiddens, config.dropout_lstm_input, config.dropout_lstm_hidden, config.mlp_arc_size, config.mlp_rel_size, config.dropout_mlp, config.choice_size, randn_init = True)
		parser.initialize(os.path.join(args.baseline_path,'model'))
		parser.set_trainable_flags(True, True, False, True, False)
		pc = parser.all_parameter_collection
	
	data_loader = MixedDataLoader([config.train_file, config.in_domain_file], [0.5, 0.5] config.num_buckets_train, vocab)
	trainer = dy.AdamTrainer(pc, config.learning_rate , config.beta_1, config.beta_2, config.epsilon)
	
	global_step = 0
	def update_parameters():
		trainer.learning_rate = config.learning_rate*config.decay**(global_step / config.decay_steps)
		trainer.update()

	epoch = 0
	best_UAS = 0.
	history = lambda x, y : open(os.path.join(config.save_dir, 'valid_history'),'a').write('%.2f %.2f\n'%(x,y))
	while global_step < config.train_iters:
		print time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()), '\nStart training epoch #%d'%(epoch, )
		epoch += 1
		for _out, _in in data_loader.get_batches(batch_size = config.train_batch_size):
			for domain, _inputs in enumerate([_out, _in]):
				words, tags, arcs, rels = _inputs
				dy.renew_cg()
				if args.domain_loss_scale > 0.:
					arc_accuracy, rel_accuracy, overall_accuracy, loss = parser.run(words, tags, arcs, rels, in_domains = [domain]*words.shape[1], domain_loss_scale = args.domain_loss_scale)
				else:
					arc_accuracy, rel_accuracy, overall_accuracy, loss = parser.run(words, tags, arcs, rels)
				loss = loss*0.5
				loss_value = loss.scalar_value()
				loss.backward()
				sys.stdout.write("Step #%d: Acc: arc %.2f, rel %.2f, overall %.2f, loss %.3f\r\r" %(global_step, arc_accuracy, rel_accuracy, overall_accuracy, loss_value))
				sys.stdout.flush()
			update_parameters()

			global_step += 1
			if global_step % config.validate_every == 0:
				print '\nTest on development set'
				LAS, UAS = test(parser, vocab, config.num_buckets_valid, config.test_batch_size, config.dev_file, os.path.join(config.save_dir, 'valid_tmp'))
				history(LAS, UAS)
				if global_step > config.save_after and UAS > best_UAS:
					best_UAS = UAS
					parser.save(config.save_model_path)